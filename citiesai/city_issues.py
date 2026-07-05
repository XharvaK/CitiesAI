from __future__ import annotations

from typing import Any

from .snapshot import pick, pick_group
from .social_stats import format_social_index, resident_population, social_index

THRESHOLDS: dict[str, float | int] = {
    "health_low": 55,
    "wellbeing_low": 55,
    "employment_low": 85,
    "congestion_warn": 0.5,
    "city_service_fill_low": 80,
    "homeless_warn": 1,
    "moving_away_warn": 1,
}

_SEMANTIC_PARTIAL_COPY: dict[str, dict[str, str]] = {
    "housing_pressure_semantics": {
        "title": "Housing data is unavailable",
        "ask_prompt": "What should I do about housing pressure in my city?",
    },
    "labor_pressure_context": {
        "title": "Labor market data is unavailable",
        "ask_prompt": "How can I improve jobs and employment in my city?",
    },
    "utility_pressure_semantics": {
        "title": "Utility data is unavailable",
        "ask_prompt": "How do I fix water and sewage service in my city?",
    },
}


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def _city_issue(
    issue_id: str,
    *,
    severity: str,
    title: str,
    detail: str,
    ask_prompt: str = "",
    hint: str = "",
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": issue_id,
        "kind": "city",
        "severity": severity,
        "title": title,
        "detail": detail,
        "hint": hint,
        "report_category": "wrong-answer",
    }
    if ask_prompt:
        entry["ask_prompt"] = ask_prompt
    return entry


def _water_pressure_issue(snapshot: dict[str, Any], health: float | int | None) -> dict[str, Any] | None:
    utility = pick_group(snapshot, "UtilityPressureSemantics")
    water_pressure = str(pick(utility, "WaterPressure", "water_pressure") or "")
    water = pick_group(utility, "Water")
    import_month = _num(pick(water, "ImportPerMonth", "import_per_month"))
    export_month = _num(pick(water, "ExportPerMonth", "export_per_month"))
    unfulfilled = _num(pick(water, "UnfulfilledConsumption", "unfulfilled_consumption"))
    fulfillment = _num(pick(water, "FulfillmentPercent", "fulfillment_percent"))

    external = pick_group(snapshot, "ExternalConnections")
    service_trade = pick(external, "ServiceTrade", "service_trade")
    trade_water = None
    if isinstance(service_trade, dict):
        trade_water = _num(service_trade.get("water"))

    triggered = water_pressure in {
        "shortage",
        "import_dependent_shortage",
        "pressure",
        "capacity_shortage",
        "import_dependent",
    }
    if trade_water is not None and trade_water > 0:
        if export_month is None or trade_water > export_month * 2:
            triggered = True

    if not triggered and health is not None and health < THRESHOLDS["health_low"]:
        status = pick(utility, "Status", "status")
        if status in ("partial", "ok") and water_pressure not in ("ok", "unknown", ""):
            triggered = True
        elif status == "partial":
            notes = pick(utility, "Notes", "notes")
            note_text = " ".join(notes) if isinstance(notes, list) else ""
            if "water" in note_text.lower() or "fresh" in note_text.lower():
                triggered = True

    if not triggered:
        return None

    parts: list[str] = []
    if fulfillment is not None:
        parts.append(f"Water fulfillment {fulfillment:.0f}%")
    if unfulfilled is not None and unfulfilled > 0:
        parts.append(f"{int(unfulfilled)} unfulfilled units")
    if import_month is not None and import_month > 0:
        parts.append(f"importing {int(import_month)} water units/month from outside")
    if health is not None:
        parts.append(f"Health {format_social_index(health)}")
    detail = " · ".join(parts) if parts else "Fresh water demand is not fully met."

    return _city_issue(
        "city_water_pressure",
        severity="warn",
        title="Water service under pressure",
        detail=detail,
        ask_prompt="How do I fix water shortages and pumping capacity?",
    )


def _water_quality_issue(
    snapshot: dict[str, Any],
    health: float | None,
) -> dict[str, Any] | None:
    """Detect likely contamination when supply volume is fine but health is poor."""
    if health is None or health >= THRESHOLDS["health_low"]:
        return None

    utility = pick_group(snapshot, "UtilityPressureSemantics")
    water_pressure = str(pick(utility, "WaterPressure", "water_pressure") or "")
    if water_pressure not in ("ok", "unknown", ""):
        return None

    water = pick_group(utility, "Water")
    unfulfilled = _num(pick(water, "UnfulfilledConsumption", "unfulfilled_consumption")) or 0
    fulfillment = _num(pick(water, "FulfillmentPercent", "fulfillment_percent"))
    consumption = _num(pick(water, "Consumption", "consumption"))

    supply_ok = unfulfilled <= 0 and (
        fulfillment is None or fulfillment >= 90 or consumption in (None, 0)
    )
    if not supply_ok:
        return None

    parts = [f"Health {format_social_index(health)}"]
    if fulfillment is not None:
        parts.append(f"water fulfillment {fulfillment:.0f}%")
    detail = " · ".join(parts) + " — supply volume looks fine; pollution or treatment may be the problem."

    return _city_issue(
        "city_water_quality",
        severity="warn",
        title="Possible contaminated water",
        detail=detail,
        ask_prompt="Citizens say the water is contaminated — what should I fix first?",
    )


def _sewage_pressure_issue(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    utility = pick_group(snapshot, "UtilityPressureSemantics")
    sewage_pressure = str(pick(utility, "SewagePressure", "sewage_pressure") or "")
    sewage = pick_group(utility, "Sewage")
    export_month = _num(pick(sewage, "ExportPerMonth", "export_per_month"))
    unfulfilled = _num(pick(sewage, "UnfulfilledConsumption", "unfulfilled_consumption"))

    external = pick_group(snapshot, "ExternalConnections")
    service_trade = pick(external, "ServiceTrade", "service_trade")
    trade_sewage = None
    if isinstance(service_trade, dict):
        trade_sewage = _num(service_trade.get("sewage"))

    triggered = sewage_pressure in {"shortage", "capacity_shortage"}
    if trade_sewage is not None and trade_sewage > 0:
        triggered = True
    if export_month is not None and export_month > 0:
        triggered = True

    if not triggered:
        return None

    parts: list[str] = []
    if unfulfilled is not None and unfulfilled > 0:
        parts.append(f"{int(unfulfilled)} unfulfilled sewage units")
    if export_month is not None and export_month > 0:
        parts.append(f"exporting {int(export_month)} sewage units/month")
    detail = " · ".join(parts) if parts else "Sewage capacity or treatment is under pressure."

    return _city_issue(
        "city_sewage_pressure",
        severity="warn",
        title="Sewage and treatment under pressure",
        detail=detail,
        ask_prompt="How do I fix sewage and water treatment in my city?",
    )


def detect_city_issues(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    population = pick_group(snapshot, "Population")
    total_pop = _num(pick(population, "TotalPopulation", "total_population"))
    if total_pop is None or total_pop <= 0:
        return []

    official = pick_group(snapshot, "OfficialCityStatistics")
    social = pick_group(official, "Social")
    finance = pick_group(official, "Finance")
    services = pick_group(official, "Services")

    residents = resident_population(snapshot)

    health = social_index(
        pick(social, "Health", "health"),
        population=residents,
    )
    wellbeing = social_index(
        pick(social, "Wellbeing", "wellbeing"),
        population=residents,
    )
    homeless = _num(pick(social, "HomelessCount", "homeless_count"))
    moving_away = _num(pick(social, "CitizensMovedAway", "citizens_moved_away"))

    if homeless is None:
        homeless = _num(pick(population, "HomelessPopulation", "homeless_population"))
    if moving_away is None:
        moving_away = _num(pick(population, "MovingAwayPopulation", "moving_away_population"))

    income = _num(pick(finance, "Income", "income"))
    expense = _num(pick(finance, "Expense", "expense"))

    education = pick_group(snapshot, "Education")
    employment = _num(pick(education, "EmploymentRatePercent", "employment_rate_percent"))
    workforce = pick_group(snapshot, "Workforce")
    unemployed = _num(
        pick(workforce, "Unemployed", "unemployed", "UnemployedWorkers", "unemployed_workers")
    )

    transport = pick_group(snapshot, "TransportProxies")
    congestion = _num(pick(transport, "CongestionIndex0To1", "congestion_index_0_to_1"))

    utility = pick_group(snapshot, "UtilityPressureSemantics")
    city_service_fill = _num(pick(utility, "CityServiceFillPercent", "city_service_fill_percent"))
    if city_service_fill is None:
        workers = _num(pick(services, "CityServiceWorkers", "city_service_workers"))
        max_workers = _num(pick(services, "CityServiceMaxWorkers", "city_service_max_workers"))
        if workers is not None and max_workers and max_workers > 0:
            city_service_fill = workers * 100.0 / max_workers

    transit_perf = pick_group(snapshot, "TransitPerformanceSemantics")
    service_gaps = pick_group(transit_perf, "ServiceGaps")
    no_service_lines = _num(pick(service_gaps, "NoServiceLines", "no_service_lines")) or 0

    issues: list[dict[str, Any]] = []

    water = _water_pressure_issue(snapshot, health)
    if water:
        issues.append(water)

    water_quality = _water_quality_issue(snapshot, health)
    if water_quality:
        issues.append(water_quality)

    sewage = _sewage_pressure_issue(snapshot)
    if sewage:
        issues.append(sewage)

    if health is not None and health < THRESHOLDS["health_low"]:
        issues.append(
            _city_issue(
                "city_health_low",
                severity="warn",
                title="City health is low",
                detail=f"Health {format_social_index(health)} — clinics, hospitals, and utilities may need attention.",
                ask_prompt="Why is city health low and what services should I add?",
            )
        )

    if wellbeing is not None and wellbeing < THRESHOLDS["wellbeing_low"]:
        issues.append(
            _city_issue(
                "city_wellbeing_low",
                severity="warn",
                title="Wellbeing is low",
                detail=f"Wellbeing {format_social_index(wellbeing)} — services, noise, or pollution may be hurting citizens.",
                ask_prompt="What is hurting wellbeing in my city?",
            )
        )

    if homeless is not None and homeless >= THRESHOLDS["homeless_warn"]:
        issues.append(
            _city_issue(
                "city_homeless",
                severity="warn",
                title="Homelessness is rising",
                detail=f"{int(homeless)} homeless citizens need housing and services.",
                ask_prompt="How do I reduce homelessness?",
            )
        )

    if moving_away is not None and moving_away >= THRESHOLDS["moving_away_warn"]:
        issues.append(
            _city_issue(
                "city_leaving",
                severity="warn",
                title="Citizens are moving away",
                detail=f"{int(moving_away)} citizens moved away recently.",
                ask_prompt="Why are citizens moving away?",
            )
        )

    if (
        income is not None
        and expense is not None
        and expense > income
        and expense > 0
    ):
        issues.append(
            _city_issue(
                "city_budget_deficit",
                severity="warn",
                title="Budget deficit",
                detail=f"Expenses {int(expense):,} exceed income {int(income):,} per month.",
                ask_prompt="What should I fix in my budget to stop running a deficit?",
            )
        )

    employment_low = (
        employment is not None and employment < THRESHOLDS["employment_low"]
    ) or (unemployed is not None and unemployed >= 10)
    if employment_low:
        detail_parts: list[str] = []
        if employment is not None:
            detail_parts.append(f"Unemployment {100 - employment:.0f}%")
        if unemployed is not None:
            detail_parts.append(f"{int(unemployed)} unemployed workers")
        issues.append(
            _city_issue(
                "city_unemployment",
                severity="warn",
                title="Jobs gap",
                detail=" · ".join(detail_parts) or "Workforce is not fully employed.",
                ask_prompt="How can I create more jobs?",
            )
        )

    if congestion is not None and congestion > THRESHOLDS["congestion_warn"]:
        severity = "warn" if congestion >= 0.7 else "info"
        issues.append(
            _city_issue(
                "city_traffic",
                severity=severity,
                title="Traffic congestion",
                detail=f"Congestion index {congestion:.2f} — roads are heavily used.",
                ask_prompt="How can I reduce traffic congestion?",
            )
        )

    if no_service_lines > 0:
        issues.append(
            _city_issue(
                "city_transit_gaps",
                severity="warn",
                title="Transit lines without service",
                detail=f"{int(no_service_lines)} transit lines have no active vehicles.",
                ask_prompt="Which transit lines need more vehicles?",
            )
        )

    if (
        city_service_fill is not None
        and city_service_fill < THRESHOLDS["city_service_fill_low"]
    ):
        issues.append(
            _city_issue(
                "city_services_understaffed",
                severity="warn",
                title="City services understaffed",
                detail=f"City service buildings are {city_service_fill:.0f}% staffed.",
                ask_prompt="Do I need more city service buildings or workers?",
            )
        )

    watched_groups = [
        ("housing_pressure_semantics", pick_group(snapshot, "HousingPressureSemantics")),
        ("labor_pressure_context", pick_group(snapshot, "LaborPressureContext")),
        ("utility_pressure_semantics", utility),
    ]
    for group_id, group in watched_groups:
        status = pick(group, "Status", "status")
        if status != "unavailable":
            continue
        copy = _SEMANTIC_PARTIAL_COPY.get(group_id)
        if not copy:
            continue
        notes = pick(group, "Notes", "notes")
        note = notes[0] if isinstance(notes, list) and notes else ""
        issues.append(
            _city_issue(
                f"city_semantic_partial_{group_id}",
                severity="info",
                title=copy["title"],
                detail=str(note)[:240] if note else f"Export group '{group_id}' is {status}.",
                ask_prompt=copy["ask_prompt"],
            )
        )

    return issues
