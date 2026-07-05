"""Agent tool definitions and execution for agentic Ask."""

from __future__ import annotations

from typing import Any

from .tool_registry import agent_tool_definitions, execute_registered_tool

TOOL_DEFINITIONS = agent_tool_definitions()


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    snapshot: dict[str, Any],
) -> str:
    return execute_registered_tool(name, arguments, snapshot=snapshot)
