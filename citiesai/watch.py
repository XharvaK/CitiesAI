"""Background watch mode with Windows toast notifications."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .city_issues import detect_city_issues
from .config import config_dir, load_config
from .constants import HISTORY_MAX_POINTS, WATCH_ALERT_COOLDOWN_SECONDS
from .dashboard import extract_headline_metrics
from .forecasts import build_forecasts
from .historian import get_historian
from .snapshot import load_snapshot_safe, snapshot_meta

_STATE_FILE = "watch_state.json"
_TOAST_LOGO_NAME = "toast-logo.png"


def _state_path() -> Path:
    return config_dir() / _STATE_FILE


def _toast_logo_source() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base = Path(meipass)
            candidates.extend(
                [
                    base / "packaging" / "assets" / "logo.png",
                    base / "citiesai" / "gui" / "static" / "logo.png",
                ]
            )
        candidates.append(Path(sys.executable).resolve().parent / "logo.png")
    else:
        root = Path(__file__).resolve().parents[1]
        candidates.extend(
            [
                root / "packaging" / "assets" / "logo.png",
                root / "citiesai" / "gui" / "static" / "logo.png",
            ]
        )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _toast_logo_uri() -> str | None:
    source = _toast_logo_source()
    if source is None:
        return None
    dest = config_dir() / _TOAST_LOGO_NAME
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file() or dest.stat().st_mtime < source.stat().st_mtime:
            shutil.copy2(source, dest)
        return dest.resolve().as_uri()
    except OSError:
        return source.resolve().as_uri()


def _toast_app_id() -> str:
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve())
    return "CitiesAI"


def build_toast_xml(title: str, message: str, *, logo_uri: str | None = None) -> str:
    image_el = ""
    if logo_uri:
        safe_uri = escape(logo_uri, {'"': "&quot;"})
        image_el = f'<image placement="appLogoOverride" hint-crop="circle" src="{safe_uri}"/>'
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<toast>"
        '<visual><binding template="ToastGeneric">'
        f"{image_el}"
        f"<text>{escape(title)}</text>"
        f"<text>{escape(message)}</text>"
        "</binding></visual>"
        "</toast>"
    )


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {"alerted": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"alerted": {}}


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def windows_toast(title: str, message: str) -> bool:
    if sys.platform != "win32":
        return False
    toast_xml = build_toast_xml(title, message, logo_uri=_toast_logo_uri())
    app_id = _toast_app_id().replace("'", "''")
    fd, xml_path = tempfile.mkstemp(suffix=".xml", prefix="citiesai-toast-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(toast_xml)
        ps_xml_path = xml_path.replace("'", "''")
        script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
$xml.Load('{ps_xml_path}')
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            timeout=10,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        try:
            os.unlink(xml_path)
        except OSError:
            pass


def _should_alert(
    state: dict[str, Any], alert_id: str, cooldown_seconds: float = WATCH_ALERT_COOLDOWN_SECONDS
) -> bool:
    alerted = state.setdefault("alerted", {})
    now = time.time()
    last = alerted.get(alert_id)
    if last and now - float(last) < cooldown_seconds:
        return False
    alerted[alert_id] = now
    return True


def evaluate_watch_alerts(snapshot: dict[str, Any], *, state: dict[str, Any] | None = None) -> list[dict[str, str]]:
    state = state if state is not None else _load_state()
    export_path = load_config().resolved_export_path()
    meta = snapshot_meta(snapshot, path=export_path)
    metrics = extract_headline_metrics(snapshot, meta)
    alerts: list[dict[str, str]] = []

    for issue in detect_city_issues(snapshot):
        if issue.get("severity") != "warn":
            continue
        alert_id = f"issue:{issue.get('id')}"
        if _should_alert(state, alert_id):
            alerts.append(
                {
                    "id": alert_id,
                    "title": str(issue.get("title", "City alert")),
                    "message": str(issue.get("detail", ""))[:200],
                }
            )

    history = get_historian().get_history(export_path=export_path, limit=HISTORY_MAX_POINTS)
    forecast = build_forecasts(history)
    for message in forecast.get("alerts", []):
        alert_id = f"forecast:{hash(message) & 0xFFFF}"
        if _should_alert(state, alert_id):
            alerts.append({"id": alert_id, "title": "CitiesAI forecast", "message": message})

    treasury = metrics.get("treasury")
    hourly = metrics.get("treasury_net_per_hour")
    if isinstance(treasury, (int, float)) and isinstance(hourly, (int, float)) and hourly < 0:
        hours = treasury / abs(hourly)
        if 0 < hours <= 2 and _should_alert(state, "treasury_critical"):
            alerts.append(
                {
                    "id": "treasury_critical",
                    "title": "Treasury critical",
                    "message": f"~{hours:.1f}h until broke at current burn ({hourly:+,.0f}/h).",
                }
            )

    if alerts:
        _save_state(state)
    return alerts


class WatchService:
    def __init__(self, *, interval_seconds: float = 15.0, use_toast: bool = True) -> None:
        self._interval = interval_seconds
        self._use_toast = use_toast
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="citiesai-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except OSError:
                pass
            self._stop.wait(self._interval)

    def tick(self) -> list[dict[str, str]]:
        cfg = load_config()
        path = cfg.resolved_export_path()
        if not path.is_file():
            return []
        snapshot, _ = load_snapshot_safe(path)
        if snapshot is None:
            return []
        get_historian().sync(path)
        alerts = evaluate_watch_alerts(snapshot)
        if self._use_toast:
            for alert in alerts:
                windows_toast(alert["title"], alert["message"])
        return alerts


_watch: WatchService | None = None


def get_watch_service() -> WatchService:
    global _watch
    if _watch is None:
        _watch = WatchService()
    return _watch
