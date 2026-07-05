"""Shared agent/MCP tool definitions and execution."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analyzers.access_gaps import analyze_access_gaps
from .analyzers.demand_factors import analyze_demand_factors
from .analyzers.transit import analyze_transit_lines
from .analyzers.utilities_services import analyze_utilities_services
from .briefing import build_mayors_briefing
from .city_issues import detect_city_issues
from .constants import HISTORY_MAX_POINTS
from .forecasts import build_forecasts
from .historian import get_historian
from .knowledge import format_knowledge_bundle, retrieve_knowledge
from .report_ops import build_and_persist_report_card
from .snapshot import pick_group, snapshot_meta
from .summary import build_city_brief


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any], dict[str, Any], Any], str]
    agentic: bool = False


def _json_result(payload: Any, *, limit: int = 8000) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)[:limit]


def _metric_group(args: dict[str, Any], snapshot: dict[str, Any], _meta: Any) -> str:
    group = str(args.get("group", ""))
    return _json_result(pick_group(snapshot, group))


def _search_wiki(args: dict[str, Any], _snapshot: dict[str, Any], _meta: Any) -> str:
    query = str(args.get("query", "")).strip()
    limit = int(args.get("limit", 5))
    bundle = retrieve_knowledge(query, limit=limit)
    return format_knowledge_bundle(bundle, query)[:6000]


def _search_encyclopedia(args: dict[str, Any], _snapshot: dict[str, Any], _meta: Any) -> str:
    query = str(args.get("query", "")).strip()
    limit = int(args.get("limit", 5))
    bundle = retrieve_knowledge(query, limit=limit)
    if bundle.encyclopedia_hits:
        lines = [
            f"- {hit.get('title', 'entry')}: {str(hit.get('snippet', ''))[:300]}"
            for hit in bundle.encyclopedia_hits[:limit]
        ]
        return "\n".join(lines)
    return "Encyclopedia unavailable or no hits."


def _city_history(args: dict[str, Any], _snapshot: dict[str, Any], _meta: Any) -> str:
    limit = int(args.get("limit", 20))
    historian = get_historian()
    historian.sync(force=True)
    history = historian.get_history(limit=limit)
    return _json_result(
        {
            "count": history["count"],
            "deltas": history.get("deltas"),
            "latest": history["points"][-1] if history["points"] else None,
        },
        limit=6000,
    )


def _transit_lines(_args: dict[str, Any], snapshot: dict[str, Any], _meta: Any) -> str:
    return _json_result(analyze_transit_lines(snapshot), limit=6000)


def _access_gaps(_args: dict[str, Any], snapshot: dict[str, Any], _meta: Any) -> str:
    return _json_result(analyze_access_gaps(snapshot), limit=6000)


def _demand_factors(_args: dict[str, Any], snapshot: dict[str, Any], _meta: Any) -> str:
    return _json_result(analyze_demand_factors(snapshot), limit=6000)


def _utilities_services(_args: dict[str, Any], snapshot: dict[str, Any], _meta: Any) -> str:
    return _json_result(analyze_utilities_services(snapshot), limit=6000)


def _city_brief(_args: dict[str, Any], snapshot: dict[str, Any], meta: Any) -> str:
    return build_city_brief(snapshot, meta)


def _detect_issues(_args: dict[str, Any], snapshot: dict[str, Any], _meta: Any) -> str:
    return _json_result(detect_city_issues(snapshot))


def _history(args: dict[str, Any], _snapshot: dict[str, Any], _meta: Any) -> str:
    limit = int(args.get("limit", 50))
    limit = max(2, min(limit, HISTORY_MAX_POINTS))
    historian = get_historian()
    historian.sync()
    return _json_result(historian.get_history(limit=limit))


def _report_card(_args: dict[str, Any], snapshot: dict[str, Any], meta: Any) -> str:
    historian = get_historian()
    historian.sync()
    return _json_result(build_and_persist_report_card(snapshot, meta, historian=historian))


def _forecasts(_args: dict[str, Any], _snapshot: dict[str, Any], _meta: Any) -> str:
    historian = get_historian()
    historian.sync()
    history = historian.get_history(limit=HISTORY_MAX_POINTS)
    return _json_result(build_forecasts(history))


def _mayors_briefing(_args: dict[str, Any], snapshot: dict[str, Any], meta: Any) -> str:
    historian = get_historian()
    historian.sync()
    return _json_result(build_mayors_briefing(snapshot, meta, historian=historian))


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "get_metric_group",
        "Return a top-level export group from the city snapshot (e.g. mobility, workforce, taxes).",
        {
            "type": "object",
            "properties": {
                "group": {
                    "type": "string",
                    "description": "Group name in PascalCase or snake_case.",
                }
            },
            "required": ["group"],
        },
        _metric_group,
        agentic=True,
    ),
    ToolSpec(
        "search_wiki",
        "Search the bundled Cities: Skylines II wiki for gameplay guidance.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
        _search_wiki,
        agentic=True,
    ),
    ToolSpec(
        "search_encyclopedia",
        "Search the in-game encyclopedia for mechanics and terminology.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
        _search_encyclopedia,
        agentic=True,
    ),
    ToolSpec(
        "get_city_history",
        "Return recent metric history and deltas for the current city.",
        {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 2, "maximum": HISTORY_MAX_POINTS},
            },
        },
        _city_history,
        agentic=True,
    ),
    ToolSpec(
        "get_transit_lines",
        "Return per-line transit diagnosis from the export.",
        {"type": "object", "properties": {}},
        _transit_lines,
        agentic=True,
    ),
    ToolSpec(
        "get_access_gaps",
        "Return transit access gap hotspots and next-line recommendations.",
        {"type": "object", "properties": {}},
        _access_gaps,
        agentic=True,
    ),
    ToolSpec(
        "get_demand_factors",
        "Return RCI demand bars and negative factor breakdown.",
        {"type": "object", "properties": {}},
        _demand_factors,
        agentic=True,
    ),
    ToolSpec(
        "get_utilities_services",
        "Return electricity, garbage, and service coverage signals.",
        {"type": "object", "properties": {}},
        _utilities_services,
        agentic=True,
    ),
    ToolSpec(
        "get_city_brief",
        "Markdown brief of the current city snapshot.",
        {"type": "object", "properties": {}},
        _city_brief,
    ),
    ToolSpec(
        "detect_issues",
        "Rule-based city pressure and issue detection.",
        {"type": "object", "properties": {}},
        _detect_issues,
    ),
    ToolSpec(
        "get_history",
        "Persistent metric history for the current city.",
        {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 2, "maximum": HISTORY_MAX_POINTS},
            },
        },
        _history,
    ),
    ToolSpec(
        "get_report_card",
        "Letter grades per city domain.",
        {"type": "object", "properties": {}},
        _report_card,
    ),
    ToolSpec(
        "get_forecasts",
        "Trend forecasts and alerts from recent history.",
        {"type": "object", "properties": {}},
        _forecasts,
    ),
    ToolSpec(
        "get_mayors_briefing",
        "Session-start briefing with digest, priorities, and grade deltas.",
        {"type": "object", "properties": {}},
        _mayors_briefing,
    ),
)

TOOL_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


def agent_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }
        for spec in TOOL_SPECS
        if spec.agentic
    ]


def mcp_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": spec.parameters,
        }
        for spec in TOOL_SPECS
    ]


def execute_registered_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    snapshot: dict[str, Any],
    meta: Any | None = None,
) -> str:
    spec = TOOL_BY_NAME.get(name)
    if spec is None:
        return _json_result({"error": f"Unknown tool: {name}"})
    if meta is None:
        meta = snapshot_meta(snapshot, path=Path("latest.json"))
    return spec.handler(arguments, snapshot, meta)
