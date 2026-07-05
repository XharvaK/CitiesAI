"""RCI demand factors from schema 2.11 demand_factors_semantics."""

from __future__ import annotations

from typing import Any

from ..snapshot import pick, pick_group

_WEAK_DEMAND_THRESHOLD = 0.35
_STRONG_NEGATIVE_FACTOR = -5


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def _factor_map(group: dict[str, Any], *keys: str) -> dict[str, int]:
    raw = pick(group, *keys)
    if not isinstance(raw, dict):
        return {}
    factors: dict[str, int] = {}
    for key, value in raw.items():
        numeric = _num(value)
        if numeric is None:
            continue
        factors[str(key)] = int(numeric)
    return factors


def _zone_label(zone: str) -> str:
    return {"residential": "Residential", "commercial": "Commercial", "industrial": "Industrial"}.get(
        zone,
        zone.title(),
    )


_FACTOR_LABELS: dict[str, str] = {
    "taxes": "Taxes",
    "happiness": "Happiness",
    "health": "Health",
    "education": "Education",
    "entertainment": "Entertainment",
    "crime": "Crime",
    "traffic": "Traffic",
    "pollution": "Pollution",
    "noise": "Noise",
    "ground_pollution": "Ground pollution",
    "air_pollution": "Air pollution",
    "unemployment": "Unemployment",
    "services": "Services",
    "transport": "Transport",
    "parks": "Parks",
    "land_value": "Land value",
}


def _humanize_factor_name(key: str) -> str:
    normalized = key.strip().lower().replace(" ", "_")
    if normalized in _FACTOR_LABELS:
        return _FACTOR_LABELS[normalized]
    if normalized.startswith("factor_"):
        suffix = normalized.split("_", 1)[-1]
        if suffix.isdigit():
            return f"Demand factor {suffix}"
    return key.replace("_", " ").title()


def _top_negative_factors(factors: dict[str, int], *, limit: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(factors.items(), key=lambda item: item[1])
    drivers: list[dict[str, Any]] = []
    for name, value in ranked:
        if value >= 0:
            break
        drivers.append(
            {
                "name": name,
                "label": _humanize_factor_name(name),
                "value": value,
            }
        )
        if len(drivers) >= limit:
            break
    return drivers


def _zone_report(
    zone: str,
    demand: float | None,
    factors: dict[str, int],
) -> dict[str, Any] | None:
    if demand is None:
        return None
    weak = demand < _WEAK_DEMAND_THRESHOLD or any(
        value <= _STRONG_NEGATIVE_FACTOR for value in factors.values()
    )
    severity = "warn" if weak else "info"
    detail = f"{_zone_label(zone)} demand {demand * 100:.0f}% of bar range"
    report: dict[str, Any] = {
        "zone": zone,
        "label": _zone_label(zone),
        "demand": round(demand, 3),
        "demand_percent": round(demand * 100, 1),
        "weak": weak,
        "severity": severity,
        "detail": detail,
        "drivers": _top_negative_factors(factors),
    }
    return report


def analyze_demand_factors(snapshot: dict[str, Any]) -> dict[str, Any]:
    group = pick_group(snapshot, "DemandFactorsSemantics")
    status = str(pick(group, "Status", "status") or "unavailable")
    if status == "unavailable":
        return {
            "ok": False,
            "status": status,
            "summary": "Demand factor export is unavailable in this snapshot.",
            "zones": [],
            "weak_zones": [],
            "ask_prompt": "Why is demand low in my city?",
        }

    residential = _num(pick(group, "ResidentialDemand", "residential_demand"))
    commercial = _num(pick(group, "CommercialDemand", "commercial_demand"))
    industrial = _num(pick(group, "IndustrialDemand", "industrial_demand"))
    residential_factors = _factor_map(group, "ResidentialFactors", "residential_factors")
    commercial_factors = _factor_map(group, "CommercialFactors", "commercial_factors")
    industrial_factors = _factor_map(group, "IndustrialFactors", "industrial_factors")

    zones: list[dict[str, Any]] = []
    for zone, demand, factors in (
        ("residential", residential, residential_factors),
        ("commercial", commercial, commercial_factors),
        ("industrial", industrial, industrial_factors),
    ):
        report = _zone_report(zone, float(demand) if demand is not None else None, factors)
        if report:
            zones.append(report)

    weak_zones = [zone for zone in zones if zone.get("weak")]
    if weak_zones:
        lead = weak_zones[0]
        summary = f"{lead['label']} demand is weak ({lead['demand_percent']:.0f}% of bar range)"
    elif zones:
        summary = "RCI demand bars are available; no zone is critically weak."
    else:
        summary = "Demand factor group is partial."

    return {
        "ok": status in ("ok", "partial") and bool(zones),
        "status": status,
        "summary": summary,
        "zones": zones,
        "weak_zones": weak_zones,
        "residential_demand": residential,
        "commercial_demand": commercial,
        "industrial_demand": industrial,
        "top_recommendation": weak_zones[0]["detail"] if weak_zones else None,
        "ask_prompt": "Why is residential or commercial demand weak in my city?",
    }
