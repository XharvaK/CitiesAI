"""Transit Line Doctor — per-line diagnosis from export semantics."""

from __future__ import annotations

from typing import Any

from ..snapshot import pick, pick_group


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def _line_diagnosis(line: dict[str, Any]) -> dict[str, Any]:
    name = str(pick(line, "LineName", "line_name") or "Unnamed line")
    mode = str(pick(line, "Mode", "mode") or "unknown")
    vehicles = _num(pick(line, "ActiveVehicleEntities", "active_vehicle_entities")) or 0
    waiting = _num(pick(line, "WaitingPassengersAllStops", "waiting_passengers_all_stops")) or 0
    onboard = _num(pick(line, "OnboardPassengersInVehicles", "onboard_passengers_in_vehicles")) or 0
    capacity = _num(pick(line, "TotalPassengerCapacity", "total_passenger_capacity")) or 0
    occupancy = _num(pick(line, "AverageVehicleOccupancyPercent", "average_vehicle_occupancy_percent"))
    round_trip_min = _num(pick(line, "ExpectedRoundTripTimeMinutes", "expected_round_trip_time_minutes"))
    active = bool(pick(line, "Active", "active"))

    issues: list[str] = []
    severity = "ok"
    diagnosis = "Operating normally."

    if not active:
        issues.append("Line is inactive")
        severity = "warn"
        diagnosis = "Line is marked inactive — check route or vehicles."

    if vehicles == 0 and active:
        issues.append("No active vehicles")
        severity = "warn"
        diagnosis = "Transit line has no vehicles running."

    if waiting >= 200:
        issues.append(f"Heavy wait queues ({int(waiting)} passengers)")
        severity = "warn"
        diagnosis = "Passengers waiting too long — add vehicles or improve frequency."

    if capacity > 0 and onboard + waiting > capacity * 1.2:
        issues.append("Demand exceeds capacity")
        severity = "warn"
        diagnosis = "Over capacity — increase fleet size or split the route."

    if occupancy is not None and occupancy < 15 and vehicles >= 2 and waiting < 20:
        issues.append(f"Low occupancy ({occupancy:.0f}%)")
        if severity == "ok":
            severity = "info"
        diagnosis = "Ghost line — few riders for the fleet size; consider cutting vehicles."

    if round_trip_min is not None and round_trip_min > 45:
        issues.append(f"Long round trip ({round_trip_min:.0f} min)")
        if severity == "ok":
            severity = "info"
        diagnosis = "Round trip is slow — check road priority or route length."

    return {
        "line_name": name,
        "mode": mode,
        "vehicles": int(vehicles),
        "waiting": int(waiting),
        "onboard": int(onboard),
        "occupancy_percent": occupancy,
        "round_trip_minutes": round_trip_min,
        "severity": severity,
        "diagnosis": diagnosis,
        "issues": issues,
        "ask_prompt": f"How can I improve transit line '{name}'?",
    }


def analyze_transit_lines(snapshot: dict[str, Any]) -> dict[str, Any]:
    group = pick_group(snapshot, "TransitLineDetailSemantics")
    status = pick(group, "Status", "status")
    lines_raw = pick(group, "Lines", "lines")
    if status == "unavailable" or not isinstance(lines_raw, list):
        return {
            "ok": False,
            "status": status or "unavailable",
            "lines": [],
            "summary": "Transit line detail data is not available in this export.",
        }

    lines = [_line_diagnosis(line) for line in lines_raw if isinstance(line, dict)]
    severity_rank = {"warn": 0, "info": 1, "ok": 2}
    lines.sort(key=lambda row: (severity_rank.get(row["severity"], 9), -row["waiting"]))

    problem_count = sum(1 for line in lines if line["severity"] != "ok")
    total_waiting = sum(line["waiting"] for line in lines)

    return {
        "ok": True,
        "status": status,
        "line_count": len(lines),
        "problem_count": problem_count,
        "total_waiting": total_waiting,
        "lines": lines,
        "summary": (
            f"{problem_count} of {len(lines)} lines need attention; "
            f"{total_waiting:,} passengers waiting system-wide."
            if lines
            else "No transit lines observed."
        ),
    }
