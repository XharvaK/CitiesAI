"""CitiesAI MCP server — expose live city state to agents."""

from __future__ import annotations

import json
import sys
from typing import Any

from .config import apply_config_to_env, load_config
from .snapshot import load_snapshot_safe, snapshot_meta
from .tool_registry import execute_registered_tool, mcp_tool_definitions
from .version import __version__

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "citiesai"
SERVER_VERSION = __version__

TOOLS = mcp_tool_definitions()


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
    return execute_registered_tool(name, arguments, snapshot=snapshot, meta=meta)


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
