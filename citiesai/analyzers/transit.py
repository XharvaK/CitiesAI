"""Transit Line Doctor — per-line diagnosis from export semantics."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..snapshot import pick, pick_group

_ISSUE_DEFS: tuple[dict[str, Any], ...] = (
    {
        "issue_id": "inactive",
        "severity": "warn",
        "title": "Inactive lines",
        "diagnosis": "Line is marked inactive — check route or vehicles.",
        "action": "Reactivate the route or assign vehicles.",
        "ask_prompt": "Why are my transit lines inactive and how do I fix them?",
    },
    {
        "issue_id": "no_vehicles",
        "severity": "warn",
        "title": "Lines without vehicles",
        "diagnosis": "Transit line has no vehicles running.",
        "action": "Add vehicles or check depot connections.",
        "ask_prompt": "How do I get vehicles running on my transit lines?",
    },
    {
        "issue_id": "heavy_wait",
        "severity": "warn",
        "title": "Heavy passenger waits",
        "diagnosis": "Passengers waiting too long — add vehicles or improve frequency.",
        "action": "Increase fleet size or headway on busy routes.",
        "ask_prompt": "How can I reduce passenger wait times on my transit network?",
    },
    {
        "issue_id": "over_capacity",
        "severity": "warn",
        "title": "Over-capacity lines",
        "diagnosis": "Over capacity — increase fleet size or split the route.",
        "action": "Add capacity or split long high-demand routes.",
        "ask_prompt": "Which transit lines need more capacity in my city?",
    },
    {
        "issue_id": "slow_round_trip",
        "severity": "info",
        "title": "Slow round trips",
        "diagnosis": "Round trip is slow — check road priority or route length.",
        "action": "Shorten routes, add transit priority, or reduce mixed traffic.",
        "ask_prompt": "How can I reduce round-trip times across my transit network?",
    },
    {
        "issue_id": "low_occupancy",
        "severity": "info",
        "title": "Low-occupancy lines",
        "diagnosis": "Ghost line — few riders for the fleet size; consider cutting vehicles.",
        "action": "Reduce fleet size or consolidate overlapping routes.",
        "ask_prompt": "Should I cut vehicles on low-ridership transit lines?",
    },
)

_ISSUE_BY_ID = {row["issue_id"]: row for row in _ISSUE_DEFS}

_HEAVY_WAIT_THRESHOLD = 200
_SLOW_ROUND_TRIP_MINUTES = 45


def _format_game_minutes(minutes: float | int) -> str:
    total = round(float(minutes))
    if total < 60:
        return f"{total} min"
    hours, rem = divmod(total, 60)
    return f"{hours}h {rem}m" if rem else f"{hours}h"


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def _issue_tags(
    *,
    active: bool,
    vehicles: int,
    waiting: int,
    onboard: int,
    capacity: float | int,
    occupancy: float | int | None,
    round_trip_min: float | int | None,
) -> list[str]:
    tags: list[str] = []
    if not active:
        tags.append("inactive")
    if vehicles == 0 and active:
        tags.append("no_vehicles")
    if waiting >= _HEAVY_WAIT_THRESHOLD:
        tags.append("heavy_wait")
    if capacity > 0 and onboard + waiting > capacity * 1.2:
        tags.append("over_capacity")
    if (
        occupancy is not None
        and occupancy < 15
        and vehicles >= 2
        and waiting < 20
    ):
        tags.append("low_occupancy")
    if round_trip_min is not None and round_trip_min > _SLOW_ROUND_TRIP_MINUTES:
        tags.append("slow_round_trip")
    return tags


def _primary_issue_id(tags: list[str]) -> str | None:
    for definition in _ISSUE_DEFS:
        issue_id = definition["issue_id"]
        if issue_id in tags:
            return issue_id
    return None


def _line_diagnosis(line: dict[str, Any]) -> dict[str, Any]:
    name = str(pick(line, "LineName", "line_name") or "Unnamed line")
    mode = str(pick(line, "Mode", "mode") or "unknown")
    vehicles = int(_num(pick(line, "ActiveVehicleEntities", "active_vehicle_entities")) or 0)
    waiting = int(_num(pick(line, "WaitingPassengersAllStops", "waiting_passengers_all_stops")) or 0)
    onboard = int(_num(pick(line, "OnboardPassengersInVehicles", "onboard_passengers_in_vehicles")) or 0)
    capacity = _num(pick(line, "TotalPassengerCapacity", "total_passenger_capacity")) or 0
    occupancy = _num(pick(line, "AverageVehicleOccupancyPercent", "average_vehicle_occupancy_percent"))
    round_trip_min = _num(pick(line, "ExpectedRoundTripTimeMinutes", "expected_round_trip_time_minutes"))
    active = bool(pick(line, "Active", "active"))

    tags = _issue_tags(
        active=active,
        vehicles=vehicles,
        onboard=onboard,
        waiting=waiting,
        capacity=capacity,
        occupancy=occupancy,
        round_trip_min=round_trip_min,
    )
    primary_issue = _primary_issue_id(tags)

    if primary_issue:
        definition = _ISSUE_BY_ID[primary_issue]
        severity = definition["severity"]
        diagnosis = definition["diagnosis"]
    else:
        severity = "ok"
        diagnosis = "Operating normally."

    issues: list[str] = []
    if not active:
        issues.append("Line is inactive")
    if vehicles == 0 and active:
        issues.append("No active vehicles")
    if waiting >= _HEAVY_WAIT_THRESHOLD:
        issues.append(f"Heavy wait queues ({waiting} passengers)")
    if capacity > 0 and onboard + waiting > capacity * 1.2:
        issues.append("Demand exceeds capacity")
    if occupancy is not None and occupancy < 15 and vehicles >= 2 and waiting < 20:
        issues.append(f"Low occupancy ({occupancy:.0f}%)")
    if round_trip_min is not None and round_trip_min > _SLOW_ROUND_TRIP_MINUTES:
        issues.append(f"Long round trip ({_format_game_minutes(round_trip_min)})")

    return {
        "line_name": name,
        "mode": mode,
        "vehicles": vehicles,
        "waiting": waiting,
        "onboard": onboard,
        "occupancy_percent": occupancy,
        "round_trip_minutes": round_trip_min,
        "primary_issue": primary_issue,
        "severity": severity,
        "diagnosis": diagnosis,
        "issues": issues,
        "ask_prompt": f"How can I improve transit line '{name}'?",
    }


def _format_modes(modes: dict[str, int]) -> str:
  parts = [f"{mode} {count}" for mode, count in sorted(modes.items(), key=lambda item: (-item[1], item[0]))]
  return ", ".join(parts)


def group_transit_problems(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for line in lines:
        issue_id = line.get("primary_issue")
        if not issue_id:
            continue
        buckets.setdefault(str(issue_id), []).append(line)

    severity_rank = {"warn": 0, "info": 1}
    groups: list[dict[str, Any]] = []
    for issue_id, bucket in buckets.items():
        definition = _ISSUE_BY_ID[issue_id]
        bucket.sort(key=lambda row: -int(row.get("waiting") or 0))
        modes = Counter(str(row.get("mode") or "unknown") for row in bucket)
        total_waiting = sum(int(row.get("waiting") or 0) for row in bucket)
        groups.append(
            {
                "issue_id": issue_id,
                "severity": definition["severity"],
                "title": definition["title"],
                "diagnosis": definition["diagnosis"],
                "action": definition["action"],
                "ask_prompt": definition["ask_prompt"],
                "line_count": len(bucket),
                "total_waiting": total_waiting,
                "modes": dict(modes),
                "sample_lines": [str(row["line_name"]) for row in bucket[:5]],
                "lines": bucket,
            }
        )

    groups.sort(
        key=lambda group: (
            severity_rank.get(str(group["severity"]), 9),
            -int(group["total_waiting"]),
            -int(group["line_count"]),
        )
    )
    return groups


def _build_summary(
    lines: list[dict[str, Any]],
    problem_count: int,
    total_waiting: int,
    problem_groups: list[dict[str, Any]],
) -> str:
    if not lines:
        return "No transit lines observed."

    if problem_count == 0:
        return f"All {len(lines)} lines look healthy; {total_waiting:,} passengers waiting system-wide."

    if len(problem_groups) == 1:
        group = problem_groups[0]
        title = str(group["title"]).lower()
        return (
            f"{group['line_count']} lines share the same issue: {title} "
            f"({total_waiting:,} passengers waiting system-wide)."
        )

    return (
        f"{problem_count} of {len(lines)} lines need attention across {len(problem_groups)} issue types; "
        f"{total_waiting:,} passengers waiting system-wide."
    )


def analyze_transit_lines(snapshot: dict[str, Any]) -> dict[str, Any]:
    group = pick_group(snapshot, "TransitLineDetailSemantics")
    status = pick(group, "Status", "status")
    lines_raw = pick(group, "Lines", "lines")
    if status == "unavailable" or not isinstance(lines_raw, list):
        return {
            "ok": False,
            "status": status or "unavailable",
            "lines": [],
            "problem_groups": [],
            "summary": "Transit line detail data is not available in this export.",
        }

    lines = [_line_diagnosis(line) for line in lines_raw if isinstance(line, dict)]
    severity_rank = {"warn": 0, "info": 1, "ok": 2}
    lines.sort(key=lambda row: (severity_rank.get(row["severity"], 9), -row["waiting"]))

    problem_groups = group_transit_problems(lines)
    problem_count = sum(1 for line in lines if line["severity"] != "ok")
    total_waiting = sum(line["waiting"] for line in lines)

    return {
        "ok": True,
        "status": status,
        "line_count": len(lines),
        "problem_count": problem_count,
        "total_waiting": total_waiting,
        "problem_groups": problem_groups,
        "lines": lines,
        "summary": _build_summary(lines, problem_count, total_waiting, problem_groups),
    }
