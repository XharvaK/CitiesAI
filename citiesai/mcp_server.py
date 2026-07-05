"""CitiesAI MCP server — expose live city state to agents."""

from __future__ import annotations

import json
import sys
from typing import Any

from .city_issues import detect_city_issues
from .config import apply_config_to_env, load_config
from .constants import HISTORY_MAX_POINTS
from .forecasts import build_forecasts
from .historian import get_historian
from .report_ops import build_and_persist_report_card
from .snapshot import load_snapshot_safe, pick_group, snapshot_meta
from .summary import build_city_brief
from .version import __version__

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "citiesai"
SERVER_VERSION = __version__

TOOLS = [
    {
        "name": "get_city_brief",
        "description": "Markdown brief of the current city snapshot.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_metric_group",
        "description": "Return a top-level export group by name.",
        "inputSchema": {
            "type": "object",
            "properties": {"group": {"type": "string"}},
            "required": ["group"],
        },
    },
    {
        "name": "detect_issues",
        "description": "Rule-based city pressure and issue detection.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_history",
        "description": "Persistent metric history for the current city.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 2, "maximum": HISTORY_MAX_POINTS}},
        },
    },
    {
        "name": "get_report_card",
        "description": "Letter grades per city domain.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_forecasts",
        "description": "Trend forecasts and alerts from recent history.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _load_live() -> tuple[dict[str, Any], Any]:
    cfg = load_config()
    path = cfg.resolved_export_path()
    snapshot, err = load_snapshot_safe(path)
    if snapshot is None:
        raise RuntimeError(err or f"Export not found: {path}")
    meta = snapshot_meta(snapshot, path=path)
    return snapshot, meta


def _call_tool(name: str, arguments: dict[str, Any]) -> str:
    known = {t["name"] for t in TOOLS}
    if name not in known:
        raise ValueError(f"Unknown tool: {name}")
    snapshot, meta = _load_live()
    if name == "get_city_brief":
        return build_city_brief(snapshot, meta)
    if name == "get_metric_group":
        group = str(arguments.get("group", ""))
        return json.dumps(pick_group(snapshot, group), ensure_ascii=False, indent=2)
    if name == "detect_issues":
        return json.dumps(detect_city_issues(snapshot), ensure_ascii=False, indent=2)
    if name == "get_history":
        limit = int(arguments.get("limit", 50))
        limit = max(2, min(limit, HISTORY_MAX_POINTS))
        historian = get_historian()
        historian.sync()
        return json.dumps(historian.get_history(limit=limit), ensure_ascii=False, indent=2)
    if name == "get_report_card":
        historian = get_historian()
        historian.sync()
        return json.dumps(
            build_and_persist_report_card(snapshot, meta, historian=historian),
            ensure_ascii=False,
            indent=2,
        )
    if name == "get_forecasts":
        historian = get_historian()
        historian.sync()
        history = historian.get_history(limit=HISTORY_MAX_POINTS)
        return json.dumps(build_forecasts(history), ensure_ascii=False, indent=2)
    raise ValueError(f"Unknown tool: {name}")


def _handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params") or {}

    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        name = str(params.get("name", ""))
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        try:
            text = _call_tool(name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": text}], "isError": False},
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }

    if req_id is None:
        return None

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        decoded = line.decode("utf-8", errors="replace").strip()
        if not decoded:
            break
        key, _, value = decoded.partition(":")
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def run_mcp_server() -> int:
    apply_config_to_env(load_config())
    while True:
        request = _read_message()
        if request is None:
            break
        response = _handle_request(request)
        if response is not None:
            _write_message(response)
    return 0


def main() -> int:
    return run_mcp_server()


if __name__ == "__main__":
    raise SystemExit(main())
