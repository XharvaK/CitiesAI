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


def extract_headline_metrics(snapshot: dict[str, Any], meta: SnapshotMeta) -> dict[str, Any]:
    city = pick_group(snapshot, "City")
    population = pick_group(snapshot, "Population")
    official = pick_group(snapshot, "OfficialCityStatistics")
    education = pick_group(snapshot, "Education")
    transport = pick_group(snapshot, "TransportProxies")
    mobility = pick_group(snapshot, "Mobility")
    workforce = pick_group(snapshot, "Workforce")

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
        "employment_percent": pick(education, "EmploymentRatePercent", "employment_rate_percent"),
        "congestion": pick(transport, "CongestionIndex0To1", "congestion_index_0_to_1"),
        "traffic_volume": pick(mobility, "TrafficVolumeIndex", "traffic_volume_index"),
        "transit_lines": pick(mobility, "LinesTotal", "lines_total"),
        "workforce_potential": pick(workforce, "TotalPotentialWorkers", "total_potential_workers"),
        "workforce_employed": pick(workforce, "EmployedWorkers", "employed_workers"),
        "workforce_unemployed": pick(workforce, "UnemployedWorkers", "unemployed_workers"),
        "signals": signals,
    }
