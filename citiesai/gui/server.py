from __future__ import annotations

import json
import mimetypes
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import webview

from ..city_name import resolve_city_display_name
from ..config import apply_config_to_env, load_config
from ..constants import HISTORY_MAX_POINTS
from ..dashboard import extract_headline_metrics
from ..env_store import load_env_file
from ..historian import get_historian
from ..snapshot import load_snapshot_safe, snapshot_meta
from ..updater import run_startup_update_check
from ..version import __version__
from ..watch import get_watch_service
from .api import (
    api_ask_stream,
    api_briefing,
    api_clear_chat,
    api_dashboard,
    api_export_report,
    api_feedback,
    api_feedback_answer,
    api_focus,
    api_hud,
    api_insights,
    api_install_mod,
    api_issues,
    api_llm_presets,
    api_onboarding_complete,
    api_save_key,
    api_setup_preview,
    api_setup_save,
    api_status,
    api_suggestions,
    api_test_key,
    api_update_check,
    api_update_dismiss,
    api_update_download,
    api_update_install,
    api_update_settings,
    api_version,
    api_watch_status,
    api_watch_toggle,
    register_focus_handler,
)
from ..single_instance import ensure_single_instance
from .auth import TOKEN_HEADER, get_session_token, init_session_token, validate_session_token
from .tray import SystemTray

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
HUD_WIDTH = 400
HUD_HEIGHT = 112
HUD_TITLE = "CitiesAI HUD"

WindowMode = Literal["native", "browser", "none"]


def _static_root():
    return resources.files("citiesai.gui.static")


def _static_file(name: str) -> bytes:
    path = _static_root().joinpath(name)
    return path.read_bytes()


def _index_html() -> bytes:
    root = _static_root()
    index = (root / "index.html").read_text(encoding="utf-8")
    token = get_session_token() or ""
    inject = f'<meta name="citiesai-token" content="{token}">'
    if inject not in index:
        index = index.replace("<head>", f"<head>\n    {inject}", 1)
    for asset in ("app.css", "app.js"):
        asset_path = root / asset
        version = int(asset_path.stat().st_mtime)
        index = index.replace(
            f'href="/static/{asset}"',
            f'href="/static/{asset}?v={version}"',
        )
        index = index.replace(
            f'src="/static/{asset}"',
            f'src="/static/{asset}?v={version}"',
        )
    return index.encode("utf-8")


def _hud_html() -> bytes:
    root = _static_root()
    hud = (root / "hud.html").read_text(encoding="utf-8")
    asset_path = root / "app.css"
    version = int(asset_path.stat().st_mtime)
    hud = hud.replace(
        'href="/static/app.css"',
        f'href="/static/app.css?v={version}"',
    )
    return hud.encode("utf-8")


class GuiBridge:
    """Pywebview js_api: native HUD overlay and tray actions."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._main_window: webview.Window | None = None
        self._hud_window: webview.Window | None = None
        self._tray: SystemTray | None = None
        self._exiting = False
        self._hud_lock = threading.Lock()

    def attach_main_window(self, window: webview.Window) -> None:
        self._main_window = window

    def attach_tray(self, tray: SystemTray) -> None:
        self._tray = tray

    def show_main(self) -> None:
        window = self._main_window
        if window is None:
            return
        window.show()
        window.restore()
        window.focus()

    def quit_app(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        if self._tray is not None:
            self._tray.stop()
            self._tray = None
        self._close_all_hud_windows()
        if self._main_window is not None:
            try:
                self._main_window.destroy()
            except Exception:
                pass

    def close_hud(self) -> dict[str, Any]:
        with self._hud_lock:
            self._close_all_hud_windows()
        return {"ok": True}

    def _hud_url(self) -> str:
        return f"{self._base_url}/hud?overlay=1"

    @staticmethod
    def _is_hud_window(window: webview.Window) -> bool:
        return getattr(window, "_title", None) == HUD_TITLE

    def _find_hud_window(self) -> webview.Window | None:
        if self._hud_window is not None and self._hud_window in webview.windows:
            return self._hud_window
        for window in webview.windows:
            if self._is_hud_window(window):
                self._hud_window = window
                return window
        self._hud_window = None
        return None

    def _close_all_hud_windows(self) -> None:
        for window in list(webview.windows):
            if self._is_hud_window(window):
                try:
                    window.destroy()
                except Exception:
                    pass
        self._hud_window = None

    def _attach_closed_handler(self, window: webview.Window) -> None:
        def _on_closed() -> None:
            if self._hud_window is window:
                self._hud_window = None

        window.events.closed += _on_closed

    def open_hud(self) -> dict[str, Any]:
        with self._hud_lock:
            existing = self._find_hud_window()
            if existing is not None:
                try:
                    existing.show()
                    existing.restore()
                    existing.focus()
                    return {"ok": True, "action": "focus"}
                except Exception:
                    self._close_all_hud_windows()

            self._hud_window = webview.create_window(
                HUD_TITLE,
                self._hud_url(),
                width=HUD_WIDTH,
                height=HUD_HEIGHT,
                min_size=(320, HUD_HEIGHT),
                resizable=True,
                frameless=True,
                on_top=True,
                easy_drag=True,
                shadow=False,
                js_api=self,
            )
            if self._hud_window is not None:
                self._attach_closed_handler(self._hud_window)
            return {"ok": True, "action": "open"}


def _guess_type(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


MAX_JSON_BODY_BYTES = 1_048_576


class CitiesAIHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    session_token: str = ""


class CitiesAIHandler(BaseHTTPRequestHandler):
    server_version = f"CitiesAI/{__version__}"

    def _require_token(self) -> bool:
        token = self.headers.get(TOKEN_HEADER) or self.headers.get(TOKEN_HEADER.lower())
        if validate_session_token(token):
            return True
        self._send_json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Invalid session token"})
        return False

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        if length > MAX_JSON_BODY_BYTES:
            raise ValueError(f"Request body too large ({length} bytes; max {MAX_JSON_BODY_BYTES})")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def _send_bytes(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(code, body, "application/json; charset=utf-8")

    def _send_sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

    def _send_static(self, name: str) -> None:
        if ".." in name or name.startswith(("/", "\\")) or "\\" in name:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid path"})
            return
        bare_name = name.split("?", 1)[0]
        safe_name = Path(bare_name).name
        if not safe_name or safe_name != Path(bare_name).name:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid path"})
            return
        try:
            body = _static_file(safe_name)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        self._send_bytes(HTTPStatus.OK, body, _guess_type(name))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"

        if route == "/":
            self._send_bytes(HTTPStatus.OK, _index_html(), "text/html; charset=utf-8")
            return
        if route == "/hud":
            self._send_bytes(HTTPStatus.OK, _hud_html(), "text/html; charset=utf-8")
            return
        if route.startswith("/static/"):
            self._send_static(route.removeprefix("/static/"))
            return

        handlers: dict[str, Any] = {
            "/api/version": api_version,
            "/api/status": api_status,
            "/api/dashboard": api_dashboard,
            "/api/focus": api_focus,
            "/api/hud": api_hud,
            "/api/insights": api_insights,
            "/api/briefing": api_briefing,
            "/api/issues": api_issues,
            "/api/suggestions": api_suggestions,
            "/api/setup": api_setup_preview,
            "/api/settings/key/test": api_test_key,
            "/api/settings/llm-presets": api_llm_presets,
            "/api/watch": api_watch_status,
            "/api/update/check": lambda: api_update_check(
                force=parse_qs(parsed.query).get("force", ["0"])[0] in {"1", "true", "yes"}
            ),
        }
        handler = handlers.get(route)
        if handler is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        try:
            if route == "/api/dashboard":
                qs = parse_qs(parsed.query)
                try:
                    limit = int(qs.get("limit", [str(HISTORY_MAX_POINTS)])[0])
                except (TypeError, ValueError):
                    limit = HISTORY_MAX_POINTS
                limit = max(10, min(limit, HISTORY_MAX_POINTS))
                result = api_dashboard(limit=limit)
            else:
                result = handler()
        except Exception as exc:  # noqa: BLE001 - return JSON for GUI clients
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return
        self._send_json(HTTPStatus.OK, result)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/")

        try:
            body = self._read_json_body()
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        if route == "/api/ask/stream":
            if not self._require_token():
                return
            self._send_sse()
            cancelled = False

            def _stream_events():
                for event in api_ask_stream(body):
                    if cancelled:
                        break
                    yield event

            try:
                for event in _stream_events():
                    self.wfile.write(event.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                cancelled = True
            except Exception as exc:  # noqa: BLE001 - best-effort error event after headers
                try:
                    err = f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                    self.wfile.write(err.encode("utf-8"))
                    self.wfile.flush()
                except OSError:
                    pass
            return

        post_handlers: dict[str, Any] = {
            "/api/setup": api_setup_save,
            "/api/onboarding/complete": api_onboarding_complete,
            "/api/settings/key": api_save_key,
            "/api/settings/key/test": api_test_key,
            "/api/install-mod": api_install_mod,
            "/api/feedback": api_feedback,
            "/api/feedback/answer": api_feedback_answer,
            "/api/watch": api_watch_toggle,
            "/api/chat/clear": api_clear_chat,
            "/api/report/export": api_export_report,
            "/api/update/settings": api_update_settings,
            "/api/update/dismiss": api_update_dismiss,
            "/api/update/download": api_update_download,
            "/api/update/install": api_update_install,
        }
        handler = post_handlers.get(route)
        if handler is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        if not self._require_token():
            return

        try:
            result = handler(body)
        except Exception as exc:  # noqa: BLE001 - return JSON for GUI clients
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
            return
        code = HTTPStatus.OK if result.get("ok", True) else HTTPStatus.BAD_REQUEST
        self._send_json(code, result)


def _wait_for_url(url: str, *, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.3) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.08)
    raise RuntimeError(f"Server did not become ready at {url}")


def _shutdown_server(server: CitiesAIHTTPServer) -> None:
    try:
        cfg = load_config()
        export_path = cfg.resolved_export_path()
        if export_path.is_file():
            snapshot, _ = load_snapshot_safe(export_path)
            if snapshot:
                meta = snapshot_meta(snapshot, path=export_path)
                metrics = extract_headline_metrics(snapshot, meta)
                city_name = resolve_city_display_name(snapshot, meta)
                get_historian().record_session_end(city_name, metrics)
    except OSError:
        pass
    get_watch_service().stop()
    server.shutdown()
    server.server_close()


def _run_console_server(server: CitiesAIHTTPServer, url: str) -> int:
    print(f"CitiesAI v{__version__} running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping GUI.")
    finally:
        _shutdown_server(server)
    return 0


def _run_native_window(server: CitiesAIHTTPServer, url: str, *, hud: bool = False) -> int:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _wait_for_url(url)
    except RuntimeError as exc:
        print(exc)
        _shutdown_server(server)
        return 1

    bridge = GuiBridge(url)
    main_window = webview.create_window(
        title=f"CitiesAI v{__version__}",
        url=url,
        width=1280,
        height=840,
        min_size=(900, 600),
        js_api=bridge,
    )
    bridge.attach_main_window(main_window)
    register_focus_handler(bridge.show_main)

    def on_closing() -> bool:
        if bridge._exiting:
            return True
        main_window.hide()
        return False

    main_window.events.closing += on_closing

    tray = SystemTray(
        on_open=bridge.show_main,
        on_exit=bridge.quit_app,
    )
    bridge.attach_tray(tray)
    tray.start()

    if hud:
        bridge.open_hud()
    webview.start()
    tray.stop()
    _shutdown_server(server)
    return 0


def run_gui(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    window: WindowMode = "native",
    hud: bool = False,
    watch: bool = False,
) -> int:
    load_env_file()
    apply_config_to_env(load_config())
    if watch:
        get_watch_service().start()
    threading.Thread(target=run_startup_update_check, daemon=True, name="citiesai-update-check").start()
    url = f"http://{host}:{port}/"
    if window == "native" and ensure_single_instance(url) == "focused":
        return 0
    try:
        server = CitiesAIHTTPServer((host, port), CitiesAIHandler)
        server.session_token = init_session_token()
    except OSError as exc:
        if window == "native" and ensure_single_instance(url) == "focused":
            return 0
        print(
            f"Could not start CitiesAI on {host}:{port} ({exc}). "
            f"Close other CitiesAI instances or try: citiesai gui --port {(port + 1)}"
        )
        return 1

    if window == "none":
        print(f"CitiesAI v{__version__} listening at {url} (no window)")
        return _run_console_server(server, url)

    if window == "browser":
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        return _run_console_server(server, url)

    return _run_native_window(server, url, hud=hud)
