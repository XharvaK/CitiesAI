"""Deterministic evidence/causes/actions enrichment for city and setup issues."""

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


def urgency_weight(item: dict[str, Any]) -> int:
    """Return urgency tier (0 = most urgent)."""
    issue_id = str(item.get("id") or "")
    if issue_id in _URGENCY_BY_ID:
        return _URGENCY_BY_ID[issue_id]
    if issue_id.startswith("grade_"):
        return 4
    severity = str(item.get("severity") or "info")
    if severity == "error" and any(
        key in issue_id for key in ("sewage", "water", "electric", "power")
    ):
        return 0
    if severity == "error":
        return 1
    return 3

_DOMAIN_BY_ID_PREFIX: dict[str, str] = {
    "city_sewage": "services",
    "city_water": "services",
    "city_electricity": "services",
    "city_utilities": "services",
    "city_garbage": "services",
    "city_healthcare": "services",
    "city_services": "services",
    "city_traffic": "transit",
    "city_transit": "transit",
    "city_budget": "economy",
    "city_unemployment": "housing",
    "city_demand": "housing",
    "city_homeless": "housing",
    "city_health": "wellbeing",
    "city_wellbeing": "wellbeing",
    "city_citizens": "wellbeing",
    "grade_economy": "economy",
    "grade_transit": "transit",
    "grade_housing": "housing",
    "grade_services": "services",
    "grade_wellbeing": "wellbeing",
}

_ADVICE_BY_ID: dict[str, dict[str, Any]] = {
    "city_sewage_pressure": {
        "domain": "services",
        "likely_causes": [
            "Sewage treatment capacity is below demand",
            "Outlets or pipes are missing near growing districts",
        ],
        "actions": [
            "Add or upgrade sewage treatment near demand",
            "Place outlets downstream of residential and industrial growth",
            "Check pipe connectivity before expanding zoning",
        ],
    },
    "city_water_pressure": {
        "domain": "services",
        "likely_causes": [
            "Fresh water production or imports are below consumption",
            "Network pressure is weak in growing districts",
        ],
        "actions": [
            "Add water pumping or treatment capacity",
            "Extend pipes to underserved areas",
            "Reduce import dependence if local capacity is available",
        ],
    },
    "city_electricity_shortage": {
        "domain": "services",
        "likely_causes": [
            "Local generation and batteries are below electricity demand",
            "New growth outpaced power plant capacity",
        ],
        "actions": [
            "Add power plants or renewable capacity",
            "Place transformers closer to demand clusters",
            "Pause power-heavy zoning until fulfillment recovers",
        ],
    },
    "city_utilities_pressure": {
        "domain": "services",
        "likely_causes": [
            "One or more utility networks are under capacity",
        ],
        "actions": [
            "Inspect power, water, and sewage fulfillment first",
            "Expand the lowest-fulfillment utility before new growth",
        ],
    },
    "city_garbage_crisis": {
        "domain": "services",
        "likely_causes": [
            "Garbage collection or processing capacity is insufficient",
        ],
        "actions": [
            "Add garbage facilities near dense districts",
            "Check collection coverage and processing backlog",
        ],
    },
    "city_unemployment": {
        "domain": "housing",
        "likely_causes": [
            "Job supply is below the working-age population",
            "Education mix may not match available workplaces",
        ],
        "actions": [
            "Zone more commercial or industrial workplaces",
            "Match school output to the jobs you are adding",
            "Improve transit access from homes to workplaces",
        ],
    },
    "city_citizens_leaving": {
        "domain": "wellbeing",
        "likely_causes": [
            "Service, job, or housing pressure is pushing residents out",
        ],
        "actions": [
            "Fix the highest-severity utility or jobs issue first",
            "Improve health, wellbeing, and housing availability",
        ],
    },
    "city_health_low": {
        "domain": "wellbeing",
        "likely_causes": [
            "Healthcare coverage or pollution is dragging health down",
        ],
        "actions": [
            "Add clinics or hospitals near dense residential areas",
            "Reduce pollution sources near homes",
        ],
    },
    "city_wellbeing_low": {
        "domain": "wellbeing",
        "likely_causes": [
            "Leisure, parks, or service access is weak",
        ],
        "actions": [
            "Add parks, leisure, and local services near homes",
            "Resolve unemployment and housing pressure if present",
        ],
    },
    "city_budget_deficit": {
        "domain": "economy",
        "likely_causes": [
            "Monthly expenses exceed income",
        ],
        "actions": [
            "Raise underpriced service fees carefully",
            "Pause expensive expansions until cashflow recovers",
            "Check loan interest and oversized service budgets",
        ],
    },
    "city_traffic": {
        "domain": "transit",
        "likely_causes": [
            "Road capacity or intersection design is congested",
        ],
        "actions": [
            "Upgrade bottleneck roads and intersections",
            "Add transit on the busiest corridors",
        ],
    },
    "city_demand_weak": {
        "domain": "housing",
        "likely_causes": [
            "RCI demand factors are suppressing growth",
        ],
        "actions": [
            "Inspect residential, commercial, and industrial demand factors",
            "Fix the weakest demand driver before rezoning",
        ],
    },
}


def _domain_for_issue(issue: dict[str, Any]) -> str:
    issue_id = str(issue.get("id") or "")
    for prefix, domain in _DOMAIN_BY_ID_PREFIX.items():
        if issue_id.startswith(prefix):
            return domain
    if issue.get("kind") != "city":
        return "setup"
    return str(issue.get("domain") or "city")


def _evidence_from_issue(issue: dict[str, Any]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    detail = str(issue.get("detail") or "").strip()
    hint = str(issue.get("hint") or "").strip()
    if detail:
        evidence.append({"label": "Measured", "value": detail})
    if hint and hint != detail:
        evidence.append({"label": "Context", "value": hint})
    session_count = int(issue.get("session_count") or 0)
    if session_count > 1:
        evidence.append(
            {
                "label": "Persistence",
                "value": f"Seen across {session_count} recent sessions",
            }
        )
    severity = str(issue.get("severity") or "info")
    evidence.append(
        {
            "label": "Severity",
            "value": {"error": "Critical", "warn": "Warning", "info": "Info"}.get(
                severity, severity
            ),
        }
    )
    return evidence


def enrich_issue_advisor(issue: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *issue* with deterministic advisor fields."""
    enriched = dict(issue)
    issue_id = str(issue.get("id") or "")
    advice = _ADVICE_BY_ID.get(issue_id, {})
    domain = str(advice.get("domain") or _domain_for_issue(issue))
    detail = str(issue.get("detail") or "").strip()
    hint = str(issue.get("hint") or "").strip()

    likely_causes = list(advice.get("likely_causes") or [])
    actions = list(advice.get("actions") or [])
    if not likely_causes and detail:
        likely_causes = [detail]
    if not actions:
        if issue.get("action_view") == "settings":
            actions = ["Open Settings and resolve the setup item"]
        elif issue.get("ask_prompt"):
            actions = ["Ask CitiesAI for a grounded next step"]
        elif hint:
            actions = [hint]
        else:
            actions = ["Inspect the related city systems and re-check after the next snapshot"]

    enriched["domain"] = domain
    enriched["evidence"] = _evidence_from_issue(issue)
    enriched["likely_causes"] = likely_causes
    enriched["actions"] = actions
    if not enriched.get("ask_prompt") and issue.get("title"):
        enriched["ask_prompt"] = f"What should I do about: {issue.get('title')}?"
    return enriched


def enrich_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_issue_advisor(issue) for issue in issues]


def rank_issues_for_queue(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort issues for the Issues queue: severity, urgency, persistence."""
    return sorted(
        issues,
        key=lambda row: (
            0 if row.get("kind") == "city" else 1,
            _SEVERITY_ORDER.get(str(row.get("severity")), 9),
            urgency_weight(row),
            -int(row.get("session_count") or 0),
            str(row.get("title") or ""),
        ),
    )
