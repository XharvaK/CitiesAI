from __future__ import annotations

from citiesai.analyzers.demand_factors import analyze_demand_factors


def test_analyze_demand_factors_unavailable() -> None:
    report = analyze_demand_factors({"demand_factors_semantics": {"status": "unavailable"}})
    assert report["ok"] is False
    assert report["zones"] == []


def test_analyze_demand_factors_flags_weak_zone() -> None:
    snapshot = {
        "demand_factors_semantics": {
            "status": "ok",
            "residential_demand": 0.22,
            "commercial_demand": 0.68,
            "industrial_demand": 0.41,
            "residential_factors": {"taxes": -12, "happiness": 3, "factor_5": -8},
        }
    }
    report = analyze_demand_factors(snapshot)
    assert report["ok"] is True
    assert len(report["weak_zones"]) == 1
    assert report["weak_zones"][0]["zone"] == "residential"
    assert report["weak_zones"][0]["detail"] == "Residential demand 22% of bar range"
    assert "Residential demand is weak (22% of bar range)" in report["summary"]
    residential = next(z for z in report["zones"] if z["zone"] == "residential")
    taxes = next(d for d in residential["drivers"] if d["name"] == "taxes")
    assert taxes["label"] == "Taxes"
    factor5 = next(d for d in residential["drivers"] if d["name"] == "factor_5")
    assert factor5["label"] == "Demand factor 5"
