from __future__ import annotations

from citiesai.analyzers.housing import analyze_housing_labor


def _snapshot_211(**overrides: object) -> dict:
    base = {
        "population": {"total_population": 50000},
        "housing_pressure_semantics": {
            "status": "ok",
            "total_households": 22000,
            "residential_building_entities": 18000,
            "homeless_households": 0,
            "moving_away_households": 0,
        },
        "labor_pressure_context": {
            "status": "ok",
            "total_jobs": 12000,
            "total_potential_workers": 10000,
            "jobs_minus_current_workers": 2000,
            "outside_worker_share_percent": 10,
            "underemployed_worker_share_percent": 5,
        },
        "labor_market_detail": {
            "status": "ok",
            "jobs_open_by_education_level": {
                "level_0": 10,
                "level_1": 20,
                "level_2": 200,
                "level_3": 80,
                "level_4": 30,
            },
            "workforce_by_education_level": {
                "workers": {
                    "level_0": 500,
                    "level_1": 800,
                    "level_2": 1200,
                    "level_3": 400,
                    "level_4": 200,
                }
            },
        },
        "workforce": {"unemployed": 500},
        "workplaces": {"open_workplaces": 150},
    }
    base.update(overrides)
    return base


def test_housing_shortage_with_schema_211_fields() -> None:
    snapshot = _snapshot_211(
        housing_pressure_semantics={
            "status": "ok",
            "total_households": 21000,
            "residential_building_entities": 18000,
        }
    )
    report = analyze_housing_labor(snapshot)
    ids = {f["id"] for f in report["findings"]}
    assert "housing_shortage" in ids


def test_jobs_gap_uses_jobs_minus_current_workers() -> None:
    report = analyze_housing_labor(_snapshot_211())
    ids = {f["id"] for f in report["findings"]}
    assert "jobs_gap" in ids


def test_underemployment_fires_with_schema_field_name() -> None:
    snapshot = _snapshot_211(
        labor_pressure_context={
            "status": "ok",
            "total_jobs": 8000,
            "total_potential_workers": 10000,
            "jobs_minus_current_workers": -2000,
            "underemployed_worker_share_percent": 22,
        }
    )
    report = analyze_housing_labor(snapshot)
    ids = {f["id"] for f in report["findings"]}
    assert "underemployed" in ids


def test_education_level_gap_from_level_maps() -> None:
    snapshot = _snapshot_211(
        labor_market_detail={
            "status": "ok",
            "jobs_open_by_education_level": {
                "level_2": 600,
                "level_3": 10,
            },
            "workforce_by_education_level": {
                "workers": {"level_2": 200, "level_3": 400}
            },
        }
    )
    report = analyze_housing_labor(snapshot)
    ids = {f["id"] for f in report["findings"]}
    assert "edu_gap_level_2" in ids


def test_legacy_field_names_still_work() -> None:
    snapshot = {
        "housing_pressure_semantics": {
            "household_count": 21000,
            "residential_building_count": 18000,
        },
        "labor_pressure_context": {
            "total_jobs": 12000,
            "total_workers": 10000,
        },
    }
    report = analyze_housing_labor(snapshot)
    ids = {f["id"] for f in report["findings"]}
    assert "housing_shortage" in ids
    assert "jobs_gap" in ids
