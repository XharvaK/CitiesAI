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
from typing import Any, Literal
from urllib.parse import urlparse

import webview

from ..config import apply_config_to_env, load_config
from ..env_store import load_env_file
from ..snapshot_history import get_history
from ..version import __version__
from .api import (
    api_ask,
    api_ask_stream,
    api_dashboard,
    api_feedback,
    api_history,
    api_install_mod,
    api_issues,
    api_onboarding_complete,
    api_save_key,
    api_setup_preview,
    api_setup_save,
    api_status,
    api_suggestions,
    api_test_key,
    api_version,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

WindowMode = Literal["native", "browser", "none"]


def _static_file(name: str) -> bytes:
    path = resources.files("citiesai.gui.static").joinpath(name)
    return path.read_bytes()


def _guess_type(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


class CitiesAIHandler(BaseHTTPRequestHandler):
    server_version = f"CitiesAI/{__version__}"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
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
        try:
            body = _static_file(name)
        except FileNotFoundError:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        self._send_bytes(HTTPStatus.OK, body, _guess_type(name))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"

        if route == "/":
            self._send_static("index.html")
            return
        if route.startswith("/static/"):
            self._send_static(route.removeprefix("/static/"))
            return

        handlers: dict[str, Any] = {
            "/api/version": api_version,
            "/api/status": api_status,
            "/api/dashboard": api_dashboard,
            "/api/brief": api_dashboard,
            "/api/history": api_history,
            "/api/issues": api_issues,
            "/api/suggestions": api_suggestions,
            "/api/setup": api_setup_preview,
            "/api/settings/key/test": api_test_key,
        }
        handler = handlers.get(route)
        if handler is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        try:
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
            self._send_sse()
            try:
                for event in api_ask_stream(body):
                    self.wfile.write(event.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:  # noqa: BLE001 - best-effort error event after headers
                try:
                    err = f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                    self.wfile.write(err.encode("utf-8"))
                    self.wfile.flush()
                except OSError:
                    pass
            return

        post_handlers: dict[str, Any] = {
            "/api/ask": api_ask,
            "/api/setup": api_setup_save,
            "/api/onboarding/complete": api_onboarding_complete,
            "/api/settings/key": api_save_key,
            "/api/settings/key/test": api_test_key,
            "/api/install-mod": api_install_mod,
            "/api/feedback": api_feedback,
        }
        handler = post_handlers.get(route)
        if handler is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
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


def _shutdown_server(server: ThreadingHTTPServer) -> None:
    get_history().stop()
    server.shutdown()
    server.server_close()


def _run_console_server(server: ThreadingHTTPServer, url: str) -> int:
    print(f"CitiesAI v{__version__} running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping GUI.")
    finally:
        _shutdown_server(server)
    return 0


def _run_native_window(server: ThreadingHTTPServer, url: str) -> int:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _wait_for_url(url)
    except RuntimeError as exc:
        print(exc)
        _shutdown_server(server)
        return 1

    webview.create_window(
        f"CitiesAI v{__version__}",
        url,
        width=1280,
        height=840,
        min_size=(900, 600),
    )
    webview.start()
    _shutdown_server(server)
    return 0


def run_gui(
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    window: WindowMode = "native",
) -> int:
    load_env_file()
    apply_config_to_env(load_config())
    get_history().start()
    try:
        server = ThreadingHTTPServer((host, port), CitiesAIHandler)
    except OSError as exc:
        print(
            f"Could not start CitiesAI on {host}:{port} ({exc}). "
            f"Close other CitiesAI instances or try: citiesai gui --port {(port + 1)}"
        )
        return 1
    url = f"http://{host}:{port}/"

    if window == "none":
        print(f"CitiesAI v{__version__} listening at {url} (no window)")
        return _run_console_server(server, url)

    if window == "browser":
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        return _run_console_server(server, url)

    return _run_native_window(server, url)
