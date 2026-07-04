from __future__ import annotations

import pytest

from citiesai.city_issues import detect_city_issues


def _base_snapshot(**overrides: object) -> dict:
    snap: dict = {
        "Population": {"total_population": 5000},
        "OfficialCityStatistics": {
            "Finance": {"income": 12000, "expense": 9000},
            "Social": {"health": 80, "wellbeing": 75},
        },
        "Education": {"employment_rate_percent": 92},
        "Workforce": {"unemployed_workers": 0},
        "TransportProxies": {"congestion_index_0_to_1": 0.2},
        "UtilityPressureSemantics": {"status": "ok", "water_pressure": "ok", "sewage_pressure": "ok"},
        "TransitPerformanceSemantics": {
            "status": "ok",
            "service_gaps": {"no_service_lines": 0},
        },
        "HousingPressureSemantics": {"status": "ok"},
        "LaborPressureContext": {"status": "ok"},
        "Mobility": {"status": "ok"},
        "EconomySignals": {"status": "ok"},
    }
    snap.update(overrides)
    return snap


def test_detect_city_issues_empty_when_no_population() -> None:
    assert detect_city_issues({"Population": {"total_population": 0}}) == []


def test_city_budget_deficit() -> None:
    snap = _base_snapshot(
        OfficialCityStatistics={
            "Finance": {"income": 5000, "expense": 9000},
            "Social": {"health": 80, "wellbeing": 75},
        }
    )
    issues = detect_city_issues(snap)
    assert any(i["id"] == "city_budget_deficit" and i["severity"] == "warn" for i in issues)


def test_city_water_pressure_from_utility_group() -> None:
    snap = _base_snapshot(
        OfficialCityStatistics={
            "Finance": {"income": 12000, "expense": 9000},
            "Social": {"health": 42, "wellbeing": 75},
        },
        UtilityPressureSemantics={
            "status": "partial",
            "water_pressure": "import_dependent_shortage",
            "water": {
                "consumption": 1000,
                "fulfilled_consumption": 800,
                "import_per_month": 1200,
                "fulfillment_percent": 80,
            },
        },
    )
    issues = detect_city_issues(snap)
    water = next(i for i in issues if i["id"] == "city_water_pressure")
    assert water["severity"] == "warn"
    assert "1200" in water["detail"]
    assert "Ask" not in water["title"]
    assert water.get("ask_prompt")


def test_city_transit_gaps() -> None:
    snap = _base_snapshot(
        TransitPerformanceSemantics={
            "status": "ok",
            "service_gaps": {"no_service_lines": 3},
        }
    )
    issues = detect_city_issues(snap)
    assert any(i["id"] == "city_transit_gaps" for i in issues)


def test_city_water_quality_when_supply_ok_but_health_low() -> None:
    snap = _base_snapshot(
        OfficialCityStatistics={
            "Finance": {"income": 12000, "expense": 9000},
            "PopulationFlow": {"population": 618},
            "Social": {"health": 30000, "wellbeing": 30000},
        },
        UtilityPressureSemantics={
            "status": "ok",
            "water_pressure": "ok",
            "sewage_pressure": "ok",
            "water": {
                "consumption": 19410,
                "fulfilled_consumption": 19410,
                "fulfillment_percent": 100,
                "unfulfilled_consumption": 0,
            },
        },
    )
    issues = detect_city_issues(snap)
    assert any(i["id"] == "city_water_quality" for i in issues)
    assert any(i["id"] == "city_health_low" for i in issues)
    assert any(i["id"] == "city_wellbeing_low" for i in issues)


def test_collect_issues_includes_city_kind() -> None:
    from citiesai.issues import collect_issues

    metrics = {
        "city_issues": [
            {
                "id": "city_health_low",
                "kind": "city",
                "severity": "warn",
                "title": "City health is low",
                "detail": "Health 40",
                "ask_prompt": "Why is city health low?",
                "report_category": "wrong-answer",
            }
        ],
        "signals": [],
    }
    issues = collect_issues(
        {
            "mod_installed": True,
            "paths": {},
            "export": {},
            "knowledge": {"encyclopedia": {"available": True}},
            "llm": {"configured": True},
        },
        metrics,
    )
    city = next(i for i in issues if i["id"] == "city_health_low")
    assert city["kind"] == "city"
