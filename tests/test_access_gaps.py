from __future__ import annotations

from citiesai.analyzers.access_gaps import analyze_access_gaps


def _hotspot(**kwargs) -> dict:
    base = {
        "hotspot_id": "hotspot_1",
        "label": "Industrial corridor",
        "center_position": {"x": 1200, "z": 800},
        "observed_trip_count": 42,
        "uncovered_share_percent": 68,
        "average_nearest_stop_distance_m": 520,
        "priority_score": 28.5,
        "sample_route_count": 2,
        "sample_routes": [{"sample_index": 0, "segment_count": 3}],
    }
    base.update(kwargs)
    return base


def test_analyze_access_gaps_partial_capture() -> None:
    report = analyze_access_gaps(
        {
            "transit_access_gap_semantics": {
                "status": "partial",
                "capture_context": {"capture_mode": "next_export_window"},
                "notes": ["transit trip capture in progress"],
            }
        }
    )
    assert report["ok"] is True
    assert report["status"] == "partial"
    assert report["hotspots"] == []
    assert "capture" in report["summary"].lower()


def test_analyze_access_gaps_unavailable() -> None:
    report = analyze_access_gaps({"transit_access_gap_semantics": {"status": "unavailable"}})
    assert report["ok"] is False
    assert report["hotspots"] == []


def test_analyze_access_gaps_ranks_hotspots_and_recommends() -> None:
    snapshot = {
        "transit_access_gap_semantics": {
            "status": "ok",
            "summary": {"hotspots_with_uncovered_demand": 2},
            "capture_context": {"capture_mode": "next_export_window", "recorded_trip_count": 100},
            "hotspots": [
                _hotspot(
                    hotspot_id="low",
                    observed_trip_count=5,
                    uncovered_share_percent=10,
                    priority_score=5,
                ),
                _hotspot(
                    hotspot_id="high",
                    observed_trip_count=80,
                    uncovered_share_percent=75,
                    priority_score=90,
                ),
            ],
        }
    }
    report = analyze_access_gaps(snapshot)
    assert report["ok"] is True
    assert report["hotspots"][0]["hotspot_id"] == "high"
    assert report["hotspots_with_uncovered_demand"] == 2
    assert report["recommendations"]
    assert "Industrial corridor" in report["top_recommendation"]


def test_analyze_access_gaps_warn_severity_for_uncovered_hotspot() -> None:
    snapshot = {
        "transit_access_gap_semantics": {
            "status": "ok",
            "summary": {"hotspots_with_uncovered_demand": 1},
            "hotspots": [_hotspot()],
        }
    }
    report = analyze_access_gaps(snapshot)
    assert report["hotspots"][0]["severity"] == "warn"
