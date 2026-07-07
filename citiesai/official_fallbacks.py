"""Fill headline metrics when official city statistics export fails."""

from __future__ import annotations

import math
from typing import Any

from .snapshot import pick, pick_group

OFFICIAL_METRIC_KEYS = (
    "treasury",
    "income",
    "expense",
    "wellbeing",
    "health",
    "crime_rate",
)


def official_stats_degraded(snapshot: dict[str, Any]) -> bool:
    official = pick_group(snapshot, "OfficialCityStatistics")
    status = str(pick(official, "Status", "status") or "").lower()
    notes = pick(official, "Notes", "notes") or []
    if any(
        "probe failed" in str(note).lower() or "assembly failed" in str(note).lower()
        for note in notes
    ):
        return True

    finance = pick_group(official, "Finance")
    money = pick(finance, "Money", "money")
    income = pick(finance, "Income", "income")
    social = pick_group(official, "Social")
    wellbeing = pick(social, "Wellbeing", "wellbeing")
    health = pick(social, "Health", "health")

    if status in {"partial", "unavailable"} and money is None and income is None:
        return True
    if status in {"partial", "unavailable"} and wellbeing is None and health is None:
        return True
    return False


def last_non_null_series_value(series: list[Any]) -> float | int | None:
    for value in reversed(series):
        if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
            return value
    return None


def fill_official_metric_gaps(
    metrics: dict[str, Any],
    history: dict[str, Any] | None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if snapshot is not None and not official_stats_degraded(snapshot):
        return metrics
    if not history:
        return metrics

    series = history.get("series") or {}
    out = dict(metrics)
    filled: list[str] = []
    for key in OFFICIAL_METRIC_KEYS:
        if out.get(key) is not None:
            continue
        fallback = last_non_null_series_value(series.get(key) or [])
        if fallback is not None:
            out[key] = fallback
            filled.append(key)

    if filled:
        out["official_stats_fallback"] = True
        out["official_stats_fallback_fields"] = filled
    return out
