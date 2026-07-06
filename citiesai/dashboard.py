from __future__ import annotations

from typing import Any

from .city_name import resolve_city_display_name
from .rates import extract_hourly_rates
from .snapshot import SnapshotMeta, pick, pick_group
from .social_stats import resident_population, social_index


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def unemployment_percent(employment_rate: Any) -> float | None:
    rate = _num(employment_rate)
    if rate is None:
        return None
    return round(100.0 - rate, 2)


def unemployment_from_workforce(workforce: dict[str, Any]) -> float | None:
    workers = _num(
        pick(
            workforce,
            "Workers",
            "workers",
            "EmployedWorkers",
            "employed_workers",
        )
    )
    unemployed = _num(
        pick(
            workforce,
            "Unemployed",
            "unemployed",
            "UnemployedWorkers",
            "unemployed_workers",
        )
    )
    if workers is None or unemployed is None:
        return None
    total = workers + unemployed
    if total <= 0:
        return None
    return round(unemployed / total * 100.0, 2)


def congestion_percent(congestion_index: Any) -> float | None:
    index = _num(congestion_index)
    if index is None:
        return None
    return round(index * 100.0, 1)


def utility_fulfillment_percent(flow: dict[str, Any]) -> float | int | None:
    """Prefer exported fulfillment; infer from capacity vs consumption when missing."""
    direct = _num(pick(flow, "FulfillmentPercent", "fulfillment_percent"))
    if direct is not None:
        return direct

    consumption = _num(pick(flow, "Consumption", "consumption"))
    capacity = _num(pick(flow, "Capacity", "capacity"))
    if consumption is None or consumption <= 0 or capacity is None:
        return None

    return round(min(capacity, consumption) / consumption * 100.0, 1)


def extract_headline_metrics(snapshot: dict[str, Any], meta: SnapshotMeta) -> dict[str, Any]:
    city = pick_group(snapshot, "City")
    population = pick_group(snapshot, "Population")
    official = pick_group(snapshot, "OfficialCityStatistics")
    education = pick_group(snapshot, "Education")
    transport = pick_group(snapshot, "TransportProxies")
    mobility = pick_group(snapshot, "Mobility")
    workforce = pick_group(snapshot, "Workforce")
    utilities = pick_group(snapshot, "UtilitiesServicesSemantics")
    utility_pressure = pick_group(snapshot, "UtilityPressureSemantics")

    time_block = pick_group(official, "Time")
    finance = pick_group(official, "Finance")
    social = pick_group(official, "Social")

    residents = resident_population(snapshot)

    income = _num(pick(finance, "Income", "income"))
    expense = _num(pick(finance, "Expense", "expense"))
    hourly = extract_hourly_rates(snapshot)

    signals: list[dict[str, str]] = []
    watch_groups: list[tuple[str, dict[str, Any]]] = [
        ("housing", pick_group(snapshot, "HousingPressureSemantics")),
        ("labor", pick_group(snapshot, "LaborPressureContext")),
        ("mobility", pick_group(snapshot, "Mobility")),
        ("economy", pick_group(snapshot, "EconomySignals")),
        ("transit", pick_group(snapshot, "TransitPerformanceSemantics")),
    ]
    for name, group in watch_groups:
        status = pick(group, "Status", "status")
        if status and status != "ok":
            notes = pick(group, "Notes", "notes")
            note = notes[0] if isinstance(notes, list) and notes else ""
            signals.append({"id": name, "status": str(status), "note": str(note)})

    return {
        "city_name": resolve_city_display_name(snapshot, meta),
        "exported_at_utc": meta.exported_at_utc,
        "age_seconds": meta.age_seconds,
        "stale": meta.stale,
        "schema_version": meta.schema_version,
        "buildings": pick(city, "BuildingCount", "building_count"),
        "districts": pick(city, "DistrictCount", "district_count"),
        "population": residents,
        "population_ecs_total": pick(population, "TotalPopulation", "total_population"),
        "homeless": pick(population, "HomelessPopulation", "homeless_population"),
        "moving_away": pick(population, "MovingAwayPopulation", "moving_away_population"),
        "game_year": pick(time_block, "GameYear", "game_year"),
        "game_month": pick(time_block, "GameMonth", "game_month"),
        "treasury": pick(finance, "Money", "money"),
        "income": income,
        "expense": expense,
        "treasury_net_per_hour": hourly["treasury_net_per_hour"],
        "population_change_per_hour": hourly["population_change_per_hour"],
        "wellbeing": social_index(
            pick(social, "Wellbeing", "wellbeing"),
            population=residents,
        ),
        "health": social_index(
            pick(social, "Health", "health"),
            population=residents,
        ),
        "crime_rate": pick(social, "CrimeRate", "crime_rate"),
        "educated_percent": pick(education, "EducatedPercent", "educated_percent"),
        "unemployment_percent": (
            unemployment_percent(
                pick(education, "EmploymentRatePercent", "employment_rate_percent")
            )
            or unemployment_from_workforce(workforce)
        ),
        "congestion_percent": congestion_percent(
            pick(transport, "CongestionIndex0To1", "congestion_index_0_to_1")
        ),
        "electricity_fulfillment_percent": pick(
            utilities,
            "ElectricityFulfillmentPercent",
            "electricity_fulfillment_percent",
        )
        or pick(
            pick_group(utility_pressure, "Electricity"),
            "FulfillmentPercent",
            "fulfillment_percent",
        ),
        "water_fulfillment_percent": utility_fulfillment_percent(
            pick_group(utility_pressure, "Water")
        ),
        "sewage_fulfillment_percent": utility_fulfillment_percent(
            pick_group(utility_pressure, "Sewage")
        ),
        "power_headline": (
            f"{pick(utilities, 'ElectricityFulfillmentPercent', 'electricity_fulfillment_percent'):.0f}% power fulfilled"
            if isinstance(
                pick(utilities, "ElectricityFulfillmentPercent", "electricity_fulfillment_percent"),
                (int, float),
            )
            else None
        ),
        "transit_lines": pick(mobility, "LinesTotal", "lines_total"),
        "workforce_potential": pick(workforce, "TotalPotentialWorkers", "total_potential_workers"),
        "workforce_employed": pick(
            workforce,
            "Workers",
            "workers",
            "EmployedWorkers",
            "employed_workers",
        ),
        "workforce_unemployed": pick(
            workforce,
            "Unemployed",
            "unemployed",
            "UnemployedWorkers",
            "unemployed_workers",
        ),
        "signals": signals,
    }
