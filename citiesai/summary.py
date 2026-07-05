from __future__ import annotations

from typing import Any

from .city_name import resolve_city_display_name
from .snapshot import SnapshotMeta, pick, pick_group
from .social_stats import format_social_index, resident_population, social_index

MONEY_FOOTNOTE = "_Amounts are in-game city currency._"


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def _fmt_money(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "n/a"
    return f"{number:,.0f}"


def _fmt_pct(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "n/a"
    return f"{number:.1f}%"


def _status_line(group: dict[str, Any]) -> str | None:
    status = pick(group, "Status", "status")
    notes = pick(group, "Notes", "notes")
    if status in (None, "ok"):
        return None
    note = ""
    if isinstance(notes, list) and notes:
        note = f" - {notes[0]}"
    return f"{status}{note}"


def _parse_schema_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            break
    return tuple(parts)


def congestion_export_notice(snapshot: dict[str, Any], meta: SnapshotMeta) -> str | None:
    transport = pick_group(snapshot, "TransportProxies")
    congestion = pick(transport, "CongestionIndex0To1", "congestion_index_0_to_1")
    if congestion is not None:
        return None
    schema = meta.schema_version or ""
    if schema and _parse_schema_version(schema) < _parse_schema_version("2.10.0"):
        return (
            "Traffic congestion is unavailable: update the CS2 Data Export mod "
            "(export schema 2.10.0+)."
        )
    return "Traffic congestion is unavailable in this export."


def build_city_brief(snapshot: dict[str, Any], meta: SnapshotMeta) -> str:
    lines: list[str] = []
    title = resolve_city_display_name(snapshot, meta)
    lines.append(f"# City brief: {title}")
    lines.append("")
    lines.append("## Snapshot")
    lines.append(f"- path: `{meta.path}`")
    if meta.schema_version:
        lines.append(f"- schema: {meta.schema_version}")
    if meta.exported_at_utc:
        lines.append(f"- exported_at_utc: {meta.exported_at_utc}")
    if meta.age_seconds is not None:
        lines.append(f"- snapshot_age_seconds: {meta.age_seconds:.0f}")
    congestion_notice = congestion_export_notice(snapshot, meta)
    if congestion_notice:
        lines.append(f"- note: {congestion_notice}")
    lines.append("")

    city = pick_group(snapshot, "City")
    population = pick_group(snapshot, "Population")
    official = pick_group(snapshot, "OfficialCityStatistics")
    education = pick_group(snapshot, "Education")
    transport = pick_group(snapshot, "TransportProxies")
    mobility = pick_group(snapshot, "Mobility")
    workforce = pick_group(snapshot, "Workforce")
    housing = pick_group(snapshot, "HousingPressureSemantics")
    labor = pick_group(snapshot, "LaborPressureContext")

    lines.append("## Headline metrics")
    building_count = pick(city, "BuildingCount", "building_count")
    district_count = pick(city, "DistrictCount", "district_count")
    residents = resident_population(snapshot)
    total_pop = residents if residents is not None else pick(population, "TotalPopulation", "total_population")
    homeless = pick(population, "HomelessPopulation", "homeless_population")
    moving_away = pick(population, "MovingAwayPopulation", "moving_away_population")

    lines.append(f"- buildings: {building_count if building_count is not None else 'n/a'}")
    lines.append(f"- districts: {district_count if district_count is not None else 'n/a'}")
    lines.append(f"- population: {total_pop if total_pop is not None else 'n/a'}")
    if homeless not in (None, 0):
        lines.append(f"- homeless: {homeless}")
    if moving_away not in (None, 0):
        lines.append(f"- moving away: {moving_away}")

    time_block = pick_group(official, "Time")
    finance = pick_group(official, "Finance")
    social = pick_group(official, "Social")
    game_year = pick(time_block, "GameYear", "game_year")
    game_month = pick(time_block, "GameMonth", "game_month")
    if game_year is not None:
        month = game_month if game_month is not None else "?"
        lines.append(f"- in-game date: year {game_year}, month {month}")

    money = pick(finance, "Money", "money")
    income = pick(finance, "Income", "income")
    expense = pick(finance, "Expense", "expense")
    showed_money = False
    if any(v is not None for v in (money, income, expense)):
        showed_money = True
        lines.append(
            f"- treasury: {_fmt_money(money)} | income {_fmt_money(income)} | expense {_fmt_money(expense)}"
        )
        income_n = _num(income) or 0
        expense_n = _num(expense) or 0
        if expense_n > income_n and expense_n > 0:
            lines.append("- signal: expenses exceed income")

    wellbeing = social_index(pick(social, "Wellbeing", "wellbeing"), population=residents)
    health = social_index(pick(social, "Health", "health"), population=residents)
    crime_rate = pick(social, "CrimeRate", "crime_rate")
    if any(v is not None for v in (wellbeing, health, crime_rate)):
        lines.append(
            f"- wellbeing: {format_social_index(wellbeing)} | "
            f"health: {format_social_index(health)} | "
            f"crime rate: {crime_rate if crime_rate is not None else 'n/a'}"
        )

    educated = pick(education, "EducatedPercent", "educated_percent")
    employment = pick(education, "EmploymentRatePercent", "employment_rate_percent")
    unemployment = (
        round(100.0 - employment, 2) if isinstance(employment, (int, float)) else None
    )
    if educated is not None or unemployment is not None:
        lines.append(
            f"- education: educated {_fmt_pct(educated)} | unemployment {_fmt_pct(unemployment)}"
        )

    congestion = pick(transport, "CongestionIndex0To1", "congestion_index_0_to_1")
    if congestion is not None:
        if isinstance(congestion, (int, float)):
            lines.append(f"- traffic congestion: {congestion * 100:.0f}%")
        else:
            lines.append(f"- traffic congestion: {congestion}")

    lines_total = pick(mobility, "LinesTotal", "lines_total")
    if lines_total is not None:
        lines.append(f"- transit lines: {lines_total}")

    potential_workers = pick(workforce, "TotalPotentialWorkers", "total_potential_workers")
    employed = pick(workforce, "Workers", "workers", "EmployedWorkers", "employed_workers")
    unemployed = pick(workforce, "Unemployed", "unemployed", "UnemployedWorkers", "unemployed_workers")
    if any(v not in (None, 0) for v in (potential_workers, employed, unemployed)):
        lines.append(
            f"- workforce: potential {potential_workers} | employed {employed} | unemployed {unemployed}"
        )

    watch_groups: list[tuple[str, dict[str, Any]]] = [
        ("housing pressure", housing),
        ("labor pressure", labor),
        ("mobility", mobility),
        ("economy signals", pick_group(snapshot, "EconomySignals")),
        ("transit performance", pick_group(snapshot, "TransitPerformanceSemantics")),
        ("company services", pick_group(snapshot, "CompanyServiceSemantics")),
    ]
    alerts = [f"- {name}: {line}" for name, group in watch_groups if (line := _status_line(group))]
    if alerts:
        lines.append("")
        lines.append("## Data quality / pressure signals")
        lines.extend(alerts)

    if showed_money:
        lines.append("")
        lines.append(MONEY_FOOTNOTE)

    lines.append("")
    lines.append(
        "_Read-only advisor context. Ground gameplay advice in wiki and Game Encyclopedia search results._"
    )
    return "\n".join(lines)
