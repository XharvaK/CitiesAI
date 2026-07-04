from __future__ import annotations

from typing import Any

from .snapshot import pick, pick_group

# CS2 finance and population-flow stats are monthly totals; one in-game month
# equals one in-game day (24 hours) in the compressed calendar.
IN_GAME_HOURS_PER_MONTH = 24


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def monthly_to_hourly(monthly: float | int | None) -> float | None:
    if monthly is None:
        return None
    return float(monthly) / IN_GAME_HOURS_PER_MONTH


def treasury_net_per_hour(income: float | int | None, expense: float | int | None) -> float | None:
    if income is None or expense is None:
        return None
    return monthly_to_hourly(income - expense)


def population_change_per_hour(
    birth_rate: float | int | None,
    death_rate: float | int | None,
    citizens_moved_in: float | int | None,
    citizens_moved_away: float | int | None,
) -> float | None:
    parts = [birth_rate, death_rate, citizens_moved_in, citizens_moved_away]
    if any(part is None for part in parts):
        return None
    monthly_delta = float(birth_rate) + float(citizens_moved_in) - float(death_rate) - float(citizens_moved_away)
    return monthly_to_hourly(monthly_delta)


def extract_hourly_rates(snapshot: dict[str, Any]) -> dict[str, float | None]:
    official = pick_group(snapshot, "OfficialCityStatistics")
    finance = pick_group(official, "Finance")
    population_flow = pick_group(official, "PopulationFlow")

    income = _num(pick(finance, "Income", "income"))
    expense = _num(pick(finance, "Expense", "expense"))
    birth_rate = _num(pick(population_flow, "BirthRate", "birth_rate"))
    death_rate = _num(pick(population_flow, "DeathRate", "death_rate"))
    moved_in = _num(pick(population_flow, "CitizensMovedIn", "citizens_moved_in"))
    moved_away = _num(pick(population_flow, "CitizensMovedAway", "citizens_moved_away"))

    return {
        "treasury_net_per_hour": treasury_net_per_hour(income, expense),
        "population_change_per_hour": population_change_per_hour(
            birth_rate, death_rate, moved_in, moved_away
        ),
    }
