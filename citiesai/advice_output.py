"""Write advisor output for optional in-game companion display."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import load_config


def advice_output_path(export_path: Path | None = None) -> Path:
    path = (export_path or load_config().resolved_export_path()).expanduser()
    return path.parent / "advice.json"


def write_advice(
    *,
    title: str,
    body: str,
    priority: str = "normal",
    issue_id: str | None = None,
    export_path: Path | None = None,
) -> Path:
    out = advice_output_path(export_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "title": title,
        "body": body,
        "priority": priority,
    }
    if issue_id:
        payload["issue_id"] = issue_id
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out
