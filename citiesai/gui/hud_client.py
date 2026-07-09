"""HTTP client for Co-Mayor: /api/hud poll and /api/ask/stream SSE."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from .auth import TOKEN_HEADER

ASK_TIMEOUT_S = 480.0
HUD_TIMEOUT_S = 5.0


def fetch_hud(base_url: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/hud"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CitiesAI-CoMayor/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=HUD_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}


def focus_main(
    base_url: str,
    token: str | None = None,
    *,
    view: str | None = None,
) -> dict[str, Any]:
    """Ask the main CitiesAI window to restore/focus, optionally switching view."""
    query = f"?view={view}" if view else ""
    url = f"{base_url.rstrip('/')}/api/focus{query}"
    headers = {"User-Agent": "CitiesAI-CoMayor/1.0"}
    if token:
        headers[TOKEN_HEADER] = token
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=HUD_TIMEOUT_S) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else {"ok": False, "error": "bad response"}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": str(exc)}


def iter_sse_events(raw: Iterator[bytes]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Parse Server-Sent Events from a byte stream."""
    buffer = ""
    for chunk in raw:
        if not chunk:
            continue
        buffer += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buffer:
            part, buffer = buffer.split("\n\n", 1)
            event, data = _parse_sse_part(part)
            if data is None:
                continue
            yield event, data


def _parse_sse_part(part: str) -> tuple[str, dict[str, Any] | None]:
    event = "message"
    data_lines: list[str] = []
    for line in part.split("\n"):
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if not data_lines:
        return event, None
    raw = "".join(data_lines)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return event, None
    if not isinstance(payload, dict):
        return event, None
    return event, payload


def ask_stream(
    base_url: str,
    token: str,
    question: str,
    *,
    on_event: Callable[[str, dict[str, Any]], None],
    should_abort: Callable[[], bool] | None = None,
    use_llm: bool = True,
    agentic: bool = True,
) -> None:
    """POST /api/ask/stream and invoke on_event for each SSE event until done/error/abort."""
    url = f"{base_url.rstrip('/')}/api/ask/stream"
    body = json.dumps(
        {"question": question, "use_llm": use_llm, "agentic": agentic}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            TOKEN_HEADER: token,
            "User-Agent": "CitiesAI-CoMayor/1.0",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=ASK_TIMEOUT_S) as response:
            finished = False

            def _chunks() -> Iterator[bytes]:
                while not finished:
                    if should_abort and should_abort():
                        return
                    piece = response.read(256)
                    if not piece:
                        return
                    yield piece

            for event, payload in iter_sse_events(_chunks()):
                on_event(event, payload)
                if event in ("done", "error"):
                    finished = True
                    return
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            payload = json.loads(body)
            if isinstance(payload, dict):
                detail = str(payload.get("error") or "").strip()
        except (OSError, json.JSONDecodeError, UnicodeError):
            detail = ""
        if exc.code == 403:
            msg = detail or "Invalid session token"
            on_event(
                "error",
                {
                    "error": (
                        f"{msg}. Co-Mayor needs a fresh session — "
                        "re-enable Co-Mayor from Settings or restart CitiesAI."
                    )
                },
            )
        else:
            on_event("error", {"error": detail or f"HTTP {exc.code}: {exc.reason}"})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        on_event("error", {"error": str(exc)})
