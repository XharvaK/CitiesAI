from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def social_index(raw: Any, *, population: int | float | None = None) -> float | None:
    """Map official social Health/Wellbeing export fields to a 0-100 index."""
    raw_n = _num(raw)
    if raw_n is not None:
        if 0 <= raw_n <= 100:
            return round(float(raw_n), 1)

        pop_n = _num(population)
        if pop_n is not None and pop_n > 0:
            per_capita = raw_n / float(pop_n)
            if 0 <= per_capita <= 100:
                return round(per_capita, 1)

    return None


def format_social_index(index: float | int | None) -> str:
    if index is None:
        return "n/a"
    return f"{index:.1f}"


def resident_population(snapshot: dict[str, Any]) -> int | float | None:
    """Prefer official residents; fall back to ECS total population."""
    from .snapshot import pick, pick_group

    official = pick_group(snapshot, "OfficialCityStatistics")
    population_flow = pick_group(official, "PopulationFlow")
    official_pop = _num(pick(population_flow, "Population", "population"))
    if official_pop is not None and official_pop > 0:
        return official_pop

    population = pick_group(snapshot, "Population")
    local_pop = _num(pick(population, "LocalPopulation", "local_population"))
    if local_pop is not None and local_pop > 0:
        return local_pop

    return _num(pick(population, "TotalPopulation", "total_population"))
