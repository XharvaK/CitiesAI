from __future__ import annotations

from citiesai.official_fallbacks import (
    fill_official_metric_gaps,
    last_non_null_series_value,
    official_stats_degraded,
)


def test_official_stats_degraded_detects_probe_failure() -> None:
    snapshot = {
        "OfficialCityStatistics": {
            "Status": "partial",
            "Notes": ["official city statistics probe failed: Object reference not set to an instance of an object"],
            "Finance": {"Money": None, "Income": None},
            "Social": {"Wellbeing": None, "Health": None},
        }
    }
    assert official_stats_degraded(snapshot) is True


def test_fill_official_metric_gaps_uses_history() -> None:
    snapshot = {
        "OfficialCityStatistics": {
            "Status": "partial",
            "Notes": ["official city statistics probe failed: boom"],
            "Finance": {"Money": None, "Income": None},
            "Social": {"Wellbeing": None, "Health": None},
        }
    }
    metrics = {
        "treasury": None,
        "income": None,
        "expense": None,
        "wellbeing": None,
        "health": None,
        "crime_rate": None,
        "population": 12000,
    }
    history = {
        "series": {
            "treasury": [None, None, 5_049_600],
            "income": [10_000, 11_000],
            "expense": [9_500],
            "wellbeing": [40.7],
            "health": [63.1],
            "crime_rate": [3],
        }
    }
    filled = fill_official_metric_gaps(metrics, history, snapshot=snapshot)
    assert filled["treasury"] == 5_049_600
    assert filled["income"] == 11_000
    assert filled["expense"] == 9_500
    assert filled["wellbeing"] == 40.7
    assert filled["health"] == 63.1
    assert filled["crime_rate"] == 3
    assert filled["official_stats_fallback"] is True


def test_last_non_null_series_value_skips_trailing_nulls() -> None:
    assert last_non_null_series_value([None, None, 42, None]) == 42
