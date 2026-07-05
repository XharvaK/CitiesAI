"""Next Line Advisor — transit access gaps from capture-window trip hotspots."""

from __future__ import annotations

from typing import Any

from ..snapshot import pick, pick_group

_UNCOVERED_SHARE_WARN = 25.0
_NEAREST_STOP_WARN_M = 400.0
_MIN_TRIPS_FOR_HOTSPOT = 3


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def _format_position(position: Any) -> str:
    if not isinstance(position, dict):
        return "map area"
    x = _num(pick(position, "X", "x"))
    z = _num(pick(position, "Z", "z"))
    if x is None or z is None:
        return "map area"
    return f"({x:,.0f}, {z:,.0f})"


def _hotspot_label(hotspot: dict[str, Any], index: int) -> str:
    label = pick(hotspot, "Label", "label")
    if label:
        return str(label)
    hotspot_id = pick(hotspot, "HotspotId", "hotspot_id")
    if hotspot_id:
        return str(hotspot_id).replace("_", " ")
    return f"Hotspot {index + 1}"


def _route_suggestion(hotspot: dict[str, Any], label: str) -> str:
    position = _format_position(pick(hotspot, "CenterPosition", "center_position"))
    trips = int(_num(pick(hotspot, "ObservedTripCount", "observed_trip_count")) or 0)
    uncovered = _num(pick(hotspot, "UncoveredSharePercent", "uncovered_share_percent"))
    nearest = _num(pick(hotspot, "AverageNearestStopDistanceM", "average_nearest_stop_distance_m"))
    routes = pick(hotspot, "SampleRoutes", "sample_routes")
    route_count = int(_num(pick(hotspot, "SampleRouteCount", "sample_route_count")) or 0)
    if isinstance(routes, list) and routes:
        route_count = max(route_count, len(routes))

    parts = [f"Connect {label} at {position}"]
    if trips:
        parts.append(f"{trips} observed trips")
    if uncovered is not None:
        parts.append(f"{uncovered:.0f}% uncovered")
    if nearest is not None:
        parts.append(f"nearest stop ~{nearest:.0f} m away")
    if route_count:
        parts.append(f"{route_count} sample route(s) in capture window")
    return " — ".join(parts)


def _priority_rank(hotspot: dict[str, Any]) -> float:
    score = _num(pick(hotspot, "PriorityScore", "priority_score"))
    if score is not None:
        return float(score)
    trips = _num(pick(hotspot, "ObservedTripCount", "observed_trip_count")) or 0
    uncovered = _num(pick(hotspot, "UncoveredSharePercent", "uncovered_share_percent")) or 0
    return float(trips) * float(uncovered)


def _analyze_hotspot(hotspot: dict[str, Any], index: int) -> dict[str, Any]:
    label = _hotspot_label(hotspot, index)
    trips = int(_num(pick(hotspot, "ObservedTripCount", "observed_trip_count")) or 0)
    uncovered = _num(pick(hotspot, "UncoveredSharePercent", "uncovered_share_percent"))
    nearest = _num(pick(hotspot, "AverageNearestStopDistanceM", "average_nearest_stop_distance_m"))
    bucket = _num(pick(hotspot, "BucketIndex", "bucket_index"))
    includes_outside = bool(pick(hotspot, "IncludesOutsideTrips", "includes_outside_trips"))

    severity = "info"
    if uncovered is not None and uncovered >= _UNCOVERED_SHARE_WARN:
        severity = "warn"
    if nearest is not None and nearest >= _NEAREST_STOP_WARN_M and trips >= _MIN_TRIPS_FOR_HOTSPOT:
        severity = "warn"

    detail_parts: list[str] = []
    if trips:
        detail_parts.append(f"{trips} observed trips")
    if uncovered is not None:
        detail_parts.append(f"{uncovered:.0f}% uncovered demand")
    if nearest is not None:
        detail_parts.append(f"nearest stop ~{nearest:.0f} m")
    if bucket is not None:
        detail_parts.append(f"priority bucket {int(bucket)}")
    if includes_outside:
        detail_parts.append("includes outside-city trips")

    return {
        "hotspot_id": str(pick(hotspot, "HotspotId", "hotspot_id") or f"hotspot_{index}"),
        "label": label,
        "position": _format_position(pick(hotspot, "CenterPosition", "center_position")),
        "observed_trip_count": trips,
        "uncovered_share_percent": uncovered,
        "average_nearest_stop_distance_m": nearest,
        "priority_score": _priority_rank(hotspot),
        "severity": severity,
        "detail": " · ".join(detail_parts) if detail_parts else "Transit coverage gap observed.",
        "suggestion": _route_suggestion(hotspot, label),
        "ask_prompt": f"Where should I build my next transit line to serve {label}?",
    }


def analyze_access_gaps(snapshot: dict[str, Any]) -> dict[str, Any]:
    group = pick_group(snapshot, "TransitAccessGapSemantics")
    status = pick(group, "Status", "status")
    summary_raw = pick(group, "Summary", "summary")
    capture = pick(group, "CaptureContext", "capture_context")
    hotspots_raw = pick(group, "Hotspots", "hotspots")

    if status == "partial":
        notes = pick(group, "Notes", "notes")
        note = notes[0] if isinstance(notes, list) and notes else ""
        capture_mode = pick(capture, "CaptureMode", "capture_mode") if isinstance(capture, dict) else None
        return {
            "ok": True,
            "status": "partial",
            "hotspots": [],
            "recommendations": [],
            "summary": (
                note
                or "Recording transit trips — hotspots appear after the capture window finishes (about 3 minutes)."
            ),
            "capture_mode": capture_mode or "next_export_window",
        }

    if status == "unavailable" or not isinstance(hotspots_raw, list):
        notes = pick(group, "Notes", "notes")
        note = notes[0] if isinstance(notes, list) and notes else ""
        return {
            "ok": False,
            "status": status or "unavailable",
            "hotspots": [],
            "recommendations": [],
            "summary": note or "Transit access gap data is not available in this export.",
            "capture_mode": pick(capture, "CaptureMode", "capture_mode") if isinstance(capture, dict) else None,
        }

    hotspots = [
        _analyze_hotspot(row, index)
        for index, row in enumerate(hotspots_raw)
        if isinstance(row, dict)
    ]
    hotspots.sort(key=lambda row: -float(row.get("priority_score") or 0))

    uncovered_total = None
    if isinstance(summary_raw, dict):
        uncovered_total = _num(
            pick(summary_raw, "HotspotsWithUncoveredDemand", "hotspots_with_uncovered_demand")
        )
    if uncovered_total is None:
        uncovered_total = sum(
            1
            for row in hotspots
            if (row.get("uncovered_share_percent") or 0) >= _UNCOVERED_SHARE_WARN
        )

    recommendations = [row["suggestion"] for row in hotspots[:5]]
    warn_hotspots = [row for row in hotspots if row["severity"] == "warn"]

    if not hotspots:
        summary = "No transit trip hotspots captured yet — play with transit disabled briefly or wait for the next capture window."
    elif warn_hotspots:
        summary = (
            f"{len(warn_hotspots)} of {len(hotspots)} hotspots lack adequate stop coverage "
            f"({int(uncovered_total)} with uncovered demand)."
        )
    else:
        summary = f"{len(hotspots)} trip hotspots observed; coverage looks reasonable."

    return {
        "ok": True,
        "status": status,
        "hotspots_total": len(hotspots),
        "hotspots_with_uncovered_demand": int(uncovered_total),
        "capture_mode": pick(capture, "CaptureMode", "capture_mode"),
        "recorded_trip_count": _num(pick(capture, "RecordedTripCount", "recorded_trip_count")),
        "hotspots": hotspots,
        "recommendations": recommendations,
        "top_recommendation": recommendations[0] if recommendations else None,
        "summary": summary,
        "ask_prompt": "Where should I build my next transit line based on uncovered passenger demand?",
    }
