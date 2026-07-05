"""Agent tool definitions and execution for agentic Ask."""

from __future__ import annotations

import json
from typing import Any

from .constants import HISTORY_MAX_POINTS
from .historian import get_historian
from .knowledge import format_knowledge_bundle, retrieve_knowledge
from .snapshot import pick_group

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_metric_group",
            "description": "Return a top-level export group from the city snapshot (e.g. mobility, workforce, taxes).",
            "parameters": {
                "type": "object",
                "properties": {
                    "group": {
                        "type": "string",
                        "description": "Group name in PascalCase or snake_case, e.g. OfficialCityStatistics, transit_line_detail_semantics.",
                    }
                },
                "required": ["group"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_wiki",
            "description": "Search the bundled Cities: Skylines II wiki for gameplay guidance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_encyclopedia",
            "description": "Search the in-game encyclopedia for mechanics and terminology.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_city_history",
            "description": "Return recent metric history and deltas for the current city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 2, "maximum": HISTORY_MAX_POINTS},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transit_lines",
            "description": "Return per-line transit diagnosis from the export.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    snapshot: dict[str, Any],
) -> str:
    if name == "get_metric_group":
        group = str(arguments.get("group", ""))
        data = pick_group(snapshot, group)
        return json.dumps(data, ensure_ascii=False, indent=2)[:8000]

    if name == "search_wiki":
        query = str(arguments.get("query", "")).strip()
        limit = int(arguments.get("limit", 5))
        bundle = retrieve_knowledge(query, limit=limit)
        return format_knowledge_bundle(bundle, query)[:6000]

    if name == "search_encyclopedia":
        query = str(arguments.get("query", "")).strip()
        limit = int(arguments.get("limit", 5))
        bundle = retrieve_knowledge(query, limit=limit)
        if bundle.encyclopedia_hits:
            lines = [
                f"- {hit.get('title', 'entry')}: {str(hit.get('snippet', ''))[:300]}"
                for hit in bundle.encyclopedia_hits[:limit]
            ]
            return "\n".join(lines)
        return "Encyclopedia unavailable or no hits."

    if name == "get_city_history":
        limit = int(arguments.get("limit", 20))
        historian = get_historian()
        historian.sync(force=True)
        history = historian.get_history(limit=limit)
        return json.dumps(
            {
                "count": history["count"],
                "deltas": history.get("deltas"),
                "latest": history["points"][-1] if history["points"] else None,
            },
            ensure_ascii=False,
            indent=2,
        )[:6000]

    if name == "get_transit_lines":
        from .analyzers.transit import analyze_transit_lines

        return json.dumps(analyze_transit_lines(snapshot), ensure_ascii=False, indent=2)[:6000]

    return json.dumps({"error": f"Unknown tool: {name}"})
