"""Spawn / manage the Co-Mayor child process (PySide6 overlay)."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from ..config import config_dir
from .overlay import close_orphan_hud_windows

HUD_MUTEX_NAME = r"Local\CitiesAI.CoMayor.v1"
HUD_HEALTH_WAIT_S = 1.5
COMAYOR_LOG_NAME = "comayor.log"


def _hud_command(base_url: str, token: str) -> list[str]:
    # Use --flag=value so tokens/URLs starting with "-" are not parsed as options.
    url_arg = f"--url={base_url}"
    token_arg = f"--token={token}"
    if getattr(sys, "frozen", False):
        # Packaged CitiesAI.exe re-enters via --hud-process.
        return [
            str(Path(sys.executable).resolve()),
            "--hud-process",
            url_arg,
            token_arg,
        ]
    # Dev: run module entry so editable installs work.
    return [
        sys.executable,
        "-m",
        "citiesai.gui.hud_app",
        url_arg,
        token_arg,
    ]


def _creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    # Detach from parent console; no new console window.
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(
        subprocess, "DETACHED_PROCESS", 0x00000008
    )


def _comayor_log_path() -> Path:
    return config_dir() / COMAYOR_LOG_NAME


def _tail_log(path: Path, *, max_chars: int = 800) -> str:
    try:
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _terminate_proc(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=1)
        except (subprocess.TimeoutExpired, OSError):
            pass


class HudProcessController:
    """Owns the Co-Mayor subprocess lifecycle for the main GUI."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen[bytes] | None = None
        self._token: str | None = None
        self._log_fp: object | None = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            if self._proc is None:
                return False
            code = self._proc.poll()
            if code is not None:
                self._proc = None
                self._token = None
                self._close_log()
                return False
            return True

    def _close_log(self) -> None:
        fp = self._log_fp
        self._log_fp = None
        if fp is None:
            return
        try:
            fp.close()  # type: ignore[union-attr]
        except OSError:
            pass

    def _open_log(self):
        path = _comayor_log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fp = open(path, "a", encoding="utf-8", errors="replace")  # noqa: SIM115
            fp.write(f"\n--- Co-Mayor spawn {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            fp.flush()
            return fp, path
        except OSError:
            return subprocess.DEVNULL, path

    def open(self, base_url: str, token: str) -> dict:
        parent_pid = os.getpid()
        with self._lock:
            alive = self._proc is not None and self._proc.poll() is None
            same_token = alive and self._token == token
            if same_token:
                keep_pid = int(self._proc.pid) if self._proc and self._proc.pid else 0
                old = None
            elif alive:
                old = self._proc
                self._proc = None
                self._token = None
                keep_pid = 0
            else:
                old = None
                keep_pid = 0

        if same_token:
            # Already running with current session token — clear stray orphans only.
            exclude = {parent_pid}
            if keep_pid:
                exclude.add(keep_pid)
            close_orphan_hud_windows(exclude_pids=exclude)
            return {"ok": True, "action": "focus"}

        if old is not None:
            _terminate_proc(old)
            self._close_log()
            time.sleep(0.1)

        # Drop detached orphans from a previous GUI session before spawn.
        close_orphan_hud_windows(exclude_pids={parent_pid})

        with self._lock:
            cmd = _hud_command(base_url.rstrip("/"), token)
            env = os.environ.copy()
            # Avoid Qt plugin discovery issues when nested under PyInstaller.
            if getattr(sys, "frozen", False):
                meipass = getattr(sys, "_MEIPASS", None)
                if meipass:
                    env.setdefault("QT_PLUGIN_PATH", str(Path(meipass) / "PySide6" / "plugins"))
            log_fp, log_path = self._open_log()
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=log_fp,
                    stderr=subprocess.STDOUT,
                    creationflags=_creation_flags(),
                    close_fds=False if sys.platform == "win32" else True,
                )
                self._token = token
                self._log_fp = log_fp if log_fp is not subprocess.DEVNULL else None
            except OSError as exc:
                self._proc = None
                self._token = None
                if log_fp is not subprocess.DEVNULL:
                    try:
                        log_fp.close()  # type: ignore[union-attr]
                    except OSError:
                        pass
                return {"ok": False, "error": str(exc)}
            proc = self._proc
            action = "restart" if old is not None else "open"
            pid = self._proc.pid

        # Health check: child must still be alive shortly after spawn.
        deadline = time.monotonic() + HUD_HEALTH_WAIT_S
        while time.monotonic() < deadline:
            code = proc.poll()
            if code is not None:
                with self._lock:
                    if self._proc is proc:
                        self._proc = None
                        self._token = None
                        self._close_log()
                tail = _tail_log(log_path)
                detail = f"Co-Mayor exited immediately (code {code})"
                if tail:
                    detail = f"{detail}. Log: {tail}"
                return {"ok": False, "error": detail, "action": action}
            time.sleep(0.1)

        return {"ok": True, "action": action, "pid": pid}

    def close(self) -> dict:
        parent_pid = os.getpid()
        with self._lock:
            proc = self._proc
            self._proc = None
            self._token = None

        if proc is not None:
            _terminate_proc(proc)
        self._close_log()

        # Kill any orphan Co-Mayor windows (previous sessions / detached).
        close_orphan_hud_windows(exclude_pids={parent_pid})
        return {"ok": True}
