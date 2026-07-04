from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from citiesai.keywords import build_search_queries, snapshot_signals
from citiesai.snapshot import load_snapshot, pick, pick_group, snapshot_meta
from citiesai.summary import build_city_brief

VENDOR_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "vendor/Cities2-DataExport/sample/latest.sample.json"
)


@pytest.fixture
def vendor_sample() -> dict:
    return load_snapshot(VENDOR_SAMPLE)


@pytest.fixture
def empty_city() -> dict:
    return {
        "SchemaVersion": "2.7.0",
        "ExportedAtUtc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "City": {"CityName": None, "BuildingCount": 26, "DistrictCount": 0},
        "Population": {"TotalPopulation": 0, "HomelessPopulation": 0, "MovingAwayPopulation": 0},
        "OfficialCityStatistics": {
            "Finance": {"Money": 2_000_000, "Income": 0, "Expense": 0},
            "Social": {"Wellbeing": 0, "Health": 0, "CrimeRate": 0},
            "Time": {"GameYear": 2026, "GameMonth": 1},
        },
        "Education": {},
        "TransportProxies": {},
        "Mobility": {"LinesTotal": 0, "TrafficVolumeIndex": 19.5, "Status": "partial"},
        "Workforce": {},
        "EconomySignals": {"Status": "unavailable"},
        "TransitPerformanceSemantics": {"Status": "partial"},
    }


def test_pick_case_insensitive() -> None:
    assert pick({"CityName": "Bay"}, "cityname") == "Bay"
    assert pick({"city_name": "Bay"}, "CityName") == "Bay"


def test_pick_group_missing() -> None:
    assert pick_group({}, "Population") == {}


def test_snapshot_meta_staleness() -> None:
    old = (datetime.now(UTC) - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
    meta = snapshot_meta({"ExportedAtUtc": old}, path=Path("latest.json"))
    assert meta.stale is True


def test_empty_city_does_not_emit_wellbeing_signals(empty_city: dict) -> None:
    signals = snapshot_signals(empty_city)
    assert "wellbeing" not in signals
    assert "health" not in signals


def test_deficit_signals(vendor_sample: dict) -> None:
    finance = vendor_sample["official_city_statistics"]["finance"]
    finance["expense"] = finance["income"] + 1000
    signals = snapshot_signals(vendor_sample)
    assert "budget" in signals


def test_word_boundary_topic_matching() -> None:
    snapshot = {"Population": {"TotalPopulation": 0}}
    queries = build_search_queries(snapshot, "renewable energy policy")
    joined = " ".join(queries)
    assert "beginner guide" not in joined


def test_new_city_topic_matching(empty_city: dict) -> None:
    queries = build_search_queries(empty_city, "what should I build first in a new city")
    assert any("beginner guide" in q for q in queries)


def test_brief_renders_vendor_sample(vendor_sample: dict) -> None:
    meta = snapshot_meta(vendor_sample, path=VENDOR_SAMPLE)
    brief = build_city_brief(vendor_sample, meta)
    assert "Evergreen Bay" in brief
    assert "173422" in brief or "population" in brief


def test_brief_renders_pascal_case(empty_city: dict) -> None:
    meta = snapshot_meta(empty_city, path=Path("latest.json"))
    brief = build_city_brief(empty_city, meta)
    assert "26" in brief
    assert "in-game city currency" in brief


def test_vendor_sample_is_valid_json() -> None:
    data = json.loads(VENDOR_SAMPLE.read_text(encoding="utf-8"))
    assert data["schema_version"] == "2.9.0"
