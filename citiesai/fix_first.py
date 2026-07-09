"""Rank top 1–3 session actions for the dashboard Fix This First card."""

from __future__ import annotations

from typing import Any

_SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}

# Lower weight = higher urgency. Symptoms (leaving/wellbeing) rank below utility crises.
_URGENCY_BY_ID: dict[str, int] = {
    "city_sewage_pressure": 0,
    "city_water_pressure": 0,
    "city_water_quality": 0,
    "city_electricity_shortage": 0,
    "city_utilities_pressure": 0,
    "city_garbage_crisis": 1,
    "city_healthcare_capacity": 1,
    "city_services_understaffed": 1,
    "city_traffic": 1,
    "city_transit_gaps": 1,
    "city_budget_deficit": 2,
    "city_unemployment": 2,
    "city_demand_weak": 2,
    "city_homeless": 3,
    "city_health_low": 3,
    "city_wellbeing_low": 3,
    "city_citizens_leaving": 3,
}

_CRITICAL_UTILITY_IDS = frozenset(
    {
        "city_sewage_pressure",
        "city_water_pressure",
        "city_water_quality",
        "city_electricity_shortage",
        "city_utilities_pressure",
    }
)


def urgency_weight(item: dict[str, Any]) -> int:
    """Return urgency tier (0 = most urgent)."""
    issue_id = str(item.get("id") or "")
    if issue_id in _URGENCY_BY_ID:
        return _URGENCY_BY_ID[issue_id]
    if issue_id.startswith("grade_"):
        return 4
    if item.get("source") == "forecast":
        return 4
    if item.get("source") == "report_card":
        return 4
    severity = str(item.get("severity") or "info")
    if severity == "error" and any(key in issue_id for key in ("sewage", "water", "electric", "power")):
        return 0
    if severity == "error":
        return 1
    return 3


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
                "session_count": int(issue.get("session_count") or 0),
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
                    "session_count": int(item.get("session_count") or 0),
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
                        "session_count": 0,
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
                "session_count": 0,
            }
        )

    seen: set[str] = set()
    ranked: list[dict[str, Any]] = []
    for item in sorted(
        candidates,
        key=lambda row: (
            _SEVERITY_ORDER.get(str(row.get("severity")), 9),
            urgency_weight(row),
            -int(row.get("session_count") or 0),
            str(row.get("title") or ""),
        ),
    ):
        key = str(item.get("id") or item.get("title"))
        if key in seen:
            continue
        seen.add(key)
        ranked.append(item)
        if len(ranked) >= 3:
            break
    return ranked
