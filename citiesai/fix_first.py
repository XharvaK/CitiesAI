"""Rank top 1–3 session actions for the dashboard Fix This First card."""

from __future__ import annotations

from typing import Any

_SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}


def build_fix_first_playbook(
    *,
    issues: list[dict[str, Any]],
    briefing: dict[str, Any] | None = None,
    report_card: dict[str, Any] | None = None,
    forecasts: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for issue in issues:
        if issue.get("kind") != "city":
            continue
        severity = str(issue.get("severity") or "info")
        candidates.append(
            {
                "id": issue.get("id"),
                "severity": severity,
                "title": issue.get("title") or "City issue",
                "detail": issue.get("detail") or "",
                "ask_prompt": issue.get("ask_prompt") or "",
                "action_view": issue.get("action_view") or "ask",
                "source": "issue",
            }
        )

    if briefing:
        for item in briefing.get("top_issues") or []:
            if not isinstance(item, dict):
                continue
            candidates.append(
                {
                    "id": item.get("id") or "briefing_priority",
                    "severity": item.get("severity") or "warn",
                    "title": item.get("title") or "Priority",
                    "detail": item.get("detail") or "",
                    "ask_prompt": item.get("ask_prompt") or "",
                    "action_view": "ask",
                    "source": "briefing",
                }
            )

    if report_card:
        domains = report_card.get("domains") or []
        scored = [
            d
            for d in domains
            if isinstance(d, dict)
            and d.get("grade") not in (None, "N/A")
            and isinstance(d.get("score"), (int, float))
        ]
        if scored:
            weakest = min(scored, key=lambda d: float(d["score"]))
            if float(weakest.get("score", 100)) < 75:
                candidates.append(
                    {
                        "id": f"grade_{weakest.get('id', 'domain')}",
                        "severity": "warn" if float(weakest["score"]) < 60 else "info",
                        "title": f"Improve {weakest.get('label', 'city domain')}",
                        "detail": weakest.get("detail") or f"Grade {weakest.get('grade')}.",
                        "ask_prompt": weakest.get("ask_prompt") or "",
                        "action_view": "insights",
                        "source": "report_card",
                    }
                )

    for alert in (forecasts or {}).get("alerts") or []:
        candidates.append(
            {
                "id": "forecast_alert",
                "severity": "info",
                "title": "Trend alert",
                "detail": str(alert),
                "ask_prompt": "",
                "action_view": "insights",
                "source": "forecast",
            }
        )

    seen: set[str] = set()
    ranked: list[dict[str, Any]] = []
    for item in sorted(
        candidates,
        key=lambda row: (_SEVERITY_ORDER.get(str(row.get("severity")), 9), str(row.get("title"))),
    ):
        key = str(item.get("id") or item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        ranked.append(item)
        if len(ranked) >= 3:
            break
    return ranked
