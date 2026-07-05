from __future__ import annotations

from citiesai.analyzers.transit import (
    _format_game_minutes,
    _line_diagnosis,
    analyze_transit_lines,
    group_transit_problems,
)


def _line(
    *,
    name: str,
    mode: str = "bus",
    waiting: int = 0,
    round_trip: float | None = None,
    vehicles: int = 2,
    active: bool = True,
    capacity: int = 100,
    onboard: int = 10,
    occupancy: float | None = 50.0,
) -> dict:
    return {
        "line_name": name,
        "mode": mode,
        "active_vehicle_entities": vehicles,
        "waiting_passengers_all_stops": waiting,
        "onboard_passengers_in_vehicles": onboard,
        "total_passenger_capacity": capacity,
        "average_vehicle_occupancy_percent": occupancy,
        "expected_round_trip_time_minutes": round_trip,
        "active": active,
    }


def test_format_game_minutes_uses_hours_when_long() -> None:
    assert _format_game_minutes(45) == "45 min"
    assert _format_game_minutes(60) == "1h"
    assert _format_game_minutes(505) == "8h 25m"


def test_primary_issue_prefers_heavy_wait_over_slow_round_trip() -> None:
    row = _line_diagnosis(_line(name="Line A", waiting=300, round_trip=60.0))
    assert row["primary_issue"] == "heavy_wait"
    assert row["diagnosis"] == "Passengers waiting too long — add vehicles or improve frequency."
    assert "slow_round_trip" not in (row["primary_issue"],)
    assert any("Long round trip" in issue for issue in row["issues"])


def test_group_transit_problems_merges_same_issue() -> None:
    lines = [
        _line_diagnosis(_line(name="T1", mode="tram", waiting=250, round_trip=50.0, capacity=500)),
        _line_diagnosis(_line(name="T2", mode="tram", waiting=210, round_trip=55.0, capacity=500)),
        _line_diagnosis(_line(name="B1", mode="bus", waiting=220, round_trip=48.0, capacity=500)),
    ]
    groups = group_transit_problems(lines)
    assert len(groups) == 1
    assert groups[0]["issue_id"] == "heavy_wait"
    assert groups[0]["line_count"] == 3
    assert groups[0]["total_waiting"] == 680
    assert groups[0]["modes"] == {"tram": 2, "bus": 1}
    assert groups[0]["sample_lines"] == ["T1", "B1", "T2"]


def test_analyze_transit_lines_dominant_summary() -> None:
    snapshot = {
        "transit_line_detail_semantics": {
            "status": "ok",
            "lines": [
                _line(name=f"Line {index}", waiting=300, round_trip=60.0)
                for index in range(3)
            ],
        }
    }
    report = analyze_transit_lines(snapshot)
    assert report["problem_count"] == 3
    assert len(report["problem_groups"]) == 1
    assert "share the same issue" in report["summary"]
    assert "heavy passenger waits" in report["summary"].lower()


def test_analyze_transit_lines_multiple_groups_summary() -> None:
    snapshot = {
        "transit_line_detail_semantics": {
            "status": "ok",
            "lines": [
                _line(name="Wait Line", waiting=300, round_trip=30.0),
                _line(name="Slow Line", waiting=10, round_trip=60.0, occupancy=80.0),
            ],
        }
    }
    report = analyze_transit_lines(snapshot)
    assert len(report["problem_groups"]) == 2
    assert "issue types" in report["summary"]


def test_analyze_transit_lines_unavailable_has_empty_groups() -> None:
    report = analyze_transit_lines({"transit_line_detail_semantics": {"status": "unavailable"}})
    assert report["ok"] is False
    assert report["problem_groups"] == []
