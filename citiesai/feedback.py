from __future__ import annotations

import json
import os
import platform
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import config_dir, load_config
from .status import collect_status_report
from .version import __version__


def feedback_dir() -> Path:
    path = config_dir() / "feedback"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _discord_webhook_url() -> str | None:
    url = os.environ.get("CITIESAI_DISCORD_WEBHOOK", "").strip()
    return url or None


def _system_info() -> dict[str, Any]:
    report = collect_status_report(load_config())
    return {
        "version": __version__,
        "platform": platform.platform(),
        "discovery_source": report.get("discovery_source"),
        "export_stale": (report.get("export") or {}).get("stale"),
        "llm_configured": (report.get("llm") or {}).get("configured"),
    }


def submit_feedback(
    *,
    category: str,
    message: str,
    contact: str | None = None,
    attach_system_info: bool = False,
    context_issue_id: str | None = None,
) -> dict[str, Any]:
    message = message.strip()
    if not message:
        return {"ok": False, "error": "Message is required."}

    payload = {
        "category": category.strip() or "general",
        "message": message,
        "contact": (contact or "").strip(),
        "submitted_at": datetime.now(UTC).isoformat(),
        "version": __version__,
    }
    if context_issue_id:
        payload["context_issue_id"] = context_issue_id
    if attach_system_info:
        payload["system"] = _system_info()

    local_path = feedback_dir() / f"feedback-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
    local_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    webhook = _discord_webhook_url()
    if not webhook:
        return {
            "ok": True,
            "mode": "local",
            "saved_to": str(local_path),
            "hint": "Discord webhook not configured. Feedback saved locally.",
        }

    embed = {
        "title": f"CitiesAI feedback: {payload['category']}",
        "description": message[:4000],
        "color": 0xD4842C,
        "fields": [
            {"name": "Version", "value": __version__, "inline": True},
            {"name": "Contact", "value": payload["contact"] or "(none)", "inline": True},
        ],
    }
    if attach_system_info:
        embed["fields"].append(
            {
                "name": "System",
                "value": json.dumps(payload["system"], indent=0)[:1000],
                "inline": False,
            }
        )
    body = json.dumps({"embeds": [embed]}).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status >= 400:
                raise RuntimeError(f"Discord returned {response.status}")
    except (urllib.error.URLError, RuntimeError) as exc:
        return {
            "ok": True,
            "mode": "local",
            "saved_to": str(local_path),
            "warning": f"Could not reach Discord: {exc}",
        }

    return {"ok": True, "mode": "discord", "saved_to": str(local_path)}
