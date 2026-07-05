from __future__ import annotations

from pathlib import Path

import pytest

from citiesai.briefing import build_mayors_briefing
from citiesai.city_issues import detect_city_issues
from citiesai.historian import CityHistorian
from citiesai.snapshot import load_snapshot, snapshot_meta


VENDOR_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "vendor/Cities2-DataExport/sample/latest.sample.json"
)


@pytest.fixture
def vendor_sample() -> dict:
    return load_snapshot(VENDOR_SAMPLE)


def test_issue_lifecycle_tracks_and_resolves(tmp_path: Path, vendor_sample: dict) -> None:
    db = tmp_path / "historian.db"
    historian = CityHistorian(db_path=db)
    city_name = "Test City"

    issues = [
        {
            "id": "city_budget_deficit",
            "kind": "city",
            "severity": "warn",
            "title": "Budget deficit",
            "detail": "Expenses exceed income",
        }
    ]
    historian.sync_tracked_issues(city_name, issues)
    enriched = historian.enrich_issues_with_lifecycle(issues, city_name=city_name)
    assert enriched[0]["session_count"] == 1

    historian.sync_tracked_issues(city_name, [])
    resolved = historian.get_resolved_history(city_name)
    assert len(resolved) == 1
    assert resolved[0]["title"] == "Budget deficit"


def test_mayors_briefing_has_text(tmp_path: Path, vendor_sample: dict) -> None:
    historian = CityHistorian(db_path=tmp_path / "historian.db")
    meta = snapshot_meta(vendor_sample, path=VENDOR_SAMPLE)
    briefing = build_mayors_briefing(vendor_sample, meta, historian=historian)
    assert "Mayor's briefing" in briefing["text"]
    assert briefing["city_name"]



def test_detect_city_issues_ignores_access_gap_hotspots() -> None:
    snapshot = {
        "population": {"total_population": 1000},
        "official_city_statistics": {
            "social": {"health": 70, "wellbeing": 70},
            "finance": {"income": 1000, "expense": 900},
            "services": {"city_service_workers": 10, "city_service_max_workers": 10},
        },
        "education": {"employment_rate_percent": 90},
        "workforce": {"unemployed": 0},
        "transport_proxies": {"congestion_index_0_to_1": 0.1},
        "utility_pressure_semantics": {"status": "ok", "city_service_fill_percent": 95},
        "transit_performance_semantics": {
            "service_gaps": {"no_service_lines": 0},
        },
        "transit_access_gap_semantics": {
            "status": "ok",
            "summary": {"hotspots_with_uncovered_demand": 3},
            "hotspots": [
                {
                    "hotspot_id": "h1",
                    "observed_trip_count": 20,
                    "uncovered_share_percent": 80,
                    "center_position": {"x": 1, "z": 2},
                }
            ],
        },
    }
    issues = detect_city_issues(snapshot)
    ids = {issue["id"] for issue in issues}
    assert "city_transit_access_gaps" not in ids
