from __future__ import annotations

from citiesai.analyzers.utilities_services import analyze_utilities_services


def test_analyze_utilities_services_unavailable() -> None:
    report = analyze_utilities_services({"utilities_services_semantics": {"status": "unavailable"}})
    assert report["ok"] is False


def test_analyze_utilities_services_flags_electricity_shortage() -> None:
    snapshot = {
        "utilities_services_semantics": {
            "status": "ok",
            "electricity_production": 900,
            "electricity_consumption": 1400,
            "electricity_capacity": 900,
            "electricity_fulfilled_consumption": 700,
            "electricity_fulfillment_percent": 50.0,
            "electricity_pressure": "shortage",
        }
    }
    report = analyze_utilities_services(snapshot)
    assert report["ok"] is True
    assert report["findings"]
    assert report["findings"][0]["id"] == "electricity_pressure"
    assert report["power_headline"] == "50% power fulfilled"
    assert any(row["id"] == "electricity" for row in report["services"])


def test_analyze_utilities_services_falls_back_to_utility_pressure_electricity() -> None:
    snapshot = {
        "utilities_services_semantics": {"status": "partial"},
        "utility_pressure_semantics": {
            "status": "ok",
            "electricity": {
                "capacity": 1200,
                "consumption": 1300,
                "fulfilled_consumption": 1100,
                "fulfillment_percent": 84.6,
            },
        },
    }
    report = analyze_utilities_services(snapshot)
    assert report["electricity_capacity"] == 1200
    assert report["electricity_fulfillment_percent"] == 84.6


def test_analyze_utilities_services_water_and_sewage_rows() -> None:
    snapshot = {
        "utilities_services_semantics": {
            "status": "ok",
            "electricity_fulfillment_percent": 100.0,
            "electricity_pressure": "ok",
            "garbage_accumulation": 1200,
        },
        "utility_pressure_semantics": {
            "status": "ok",
            "water_pressure": "shortage",
            "sewage_pressure": "capacity_shortage",
            "water": {
                "fulfillment_percent": 72.0,
                "unfulfilled_consumption": 400,
            },
            "sewage": {
                "fulfillment_percent": 81.0,
                "unfulfilled_consumption": 250,
            },
            "city_service_fill_percent": 92.0,
        },
    }
    report = analyze_utilities_services(snapshot)
    assert report["ok"] is True
    service_ids = {row["id"] for row in report["services"]}
    assert {"electricity", "water", "sewage", "garbage", "city_services"} <= service_ids
    assert any(f["id"] == "water_pressure" for f in report["findings"])
    assert any(f["id"] == "sewage_pressure" for f in report["findings"])


def test_analyze_utilities_services_city_service_understaffed() -> None:
    snapshot = {
        "utilities_services_semantics": {
            "status": "ok",
            "electricity_fulfillment_percent": 100.0,
            "electricity_pressure": "ok",
            "garbage_accumulation": 100,
        },
        "utility_pressure_semantics": {
            "status": "ok",
            "water_pressure": "ok",
            "sewage_pressure": "ok",
            "water": {"fulfillment_percent": 100.0},
            "sewage": {"fulfillment_percent": 100.0},
            "city_service_fill_percent": 62.0,
        },
    }
    report = analyze_utilities_services(snapshot)
    assert any(f["id"] == "city_services_understaffed" for f in report["findings"])
    city_row = next(row for row in report["services"] if row["id"] == "city_services")
    assert city_row["severity"] == "warn"


def test_analyze_utilities_services_all_clear_rows() -> None:
    snapshot = {
        "utilities_services_semantics": {
            "status": "ok",
            "electricity_fulfillment_percent": 100.0,
            "electricity_pressure": "ok",
            "garbage_accumulation": 1200,
        },
        "utility_pressure_semantics": {
            "status": "ok",
            "water_pressure": "ok",
            "sewage_pressure": "ok",
            "water": {"fulfillment_percent": 100.0},
            "sewage": {"fulfillment_percent": 100.0},
            "city_service_fill_percent": 94.0,
        },
    }
    report = analyze_utilities_services(snapshot)
    assert report["ok"] is True
    assert not report["findings"]
    assert len(report["services"]) >= 5
    assert all(row["severity"] == "ok" for row in report["services"])


def test_analyze_utilities_services_hides_city_services_without_staffing_data() -> None:
    snapshot = {
        "utilities_services_semantics": {
            "status": "ok",
            "electricity_fulfillment_percent": 100.0,
            "electricity_pressure": "ok",
            "garbage_accumulation": 1200,
        },
        "utility_pressure_semantics": {
            "status": "ok",
            "water_pressure": "ok",
            "sewage_pressure": "ok",
            "water": {"fulfillment_percent": 100.0},
            "sewage": {"fulfillment_percent": 100.0},
            "city_service_fill_percent": None,
        },
        "official_city_statistics": {
            "city_services": {
                "city_service_workers": 0,
                "city_service_max_workers": 0,
            }
        },
    }
    report = analyze_utilities_services(snapshot)
    service_ids = {row["id"] for row in report["services"]}
    assert "city_services" not in service_ids
