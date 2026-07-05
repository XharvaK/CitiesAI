"""Electricity, water, sewage, garbage, and city-service staffing from export schema."""

from __future__ import annotations

from typing import Any

from ..snapshot import pick, pick_group

_ELECTRICITY_PRESSURE_WARN = {"shortage", "capacity_shortage", "pressure"}
_WATER_PRESSURE_WARN = {
    "shortage",
    "import_dependent_shortage",
    "pressure",
    "capacity_shortage",
    "import_dependent",
}
_SEWAGE_PRESSURE_WARN = {"shortage", "capacity_shortage"}
_GARBAGE_ACCUMULATION_WARN = 50_000
_CITY_SERVICE_FILL_LOW = 80


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def _service_row(
    *,
    row_id: str,
    label: str,
    detail: str,
    severity: str = "ok",
) -> dict[str, Any]:
    return {
        "id": row_id,
        "label": label,
        "detail": detail,
        "severity": severity,
    }


def _fulfillment_detail(fulfillment: float | int | None, *, noun: str) -> str:
    if fulfillment is not None:
        return f"{fulfillment:.0f}% {noun} fulfilled"
    return f"{noun.capitalize()} data unavailable"


def _water_pressure_triggered(
    utility: dict[str, Any],
    water: dict[str, Any],
    snapshot: dict[str, Any],
) -> bool:
    water_pressure = str(pick(utility, "WaterPressure", "water_pressure") or "")
    if water_pressure in _WATER_PRESSURE_WARN:
        return True

    external = pick_group(snapshot, "ExternalConnections")
    service_trade = pick(external, "ServiceTrade", "service_trade")
    trade_water = None
    if isinstance(service_trade, dict):
        trade_water = _num(service_trade.get("water"))
    export_month = _num(pick(water, "ExportPerMonth", "export_per_month"))
    if trade_water is not None and trade_water > 0:
        if export_month is None or trade_water > export_month * 2:
            return True
    return False


def _sewage_pressure_triggered(
    utility: dict[str, Any],
    sewage: dict[str, Any],
    snapshot: dict[str, Any],
) -> bool:
    sewage_pressure = str(pick(utility, "SewagePressure", "sewage_pressure") or "")
    if sewage_pressure in _SEWAGE_PRESSURE_WARN:
        return True

    external = pick_group(snapshot, "ExternalConnections")
    service_trade = pick(external, "ServiceTrade", "service_trade")
    trade_sewage = None
    if isinstance(service_trade, dict):
        trade_sewage = _num(service_trade.get("sewage"))
    export_month = _num(pick(sewage, "ExportPerMonth", "export_per_month"))
    if trade_sewage is not None and trade_sewage > 0:
        return True
    if export_month is not None and export_month > 0:
        return True
    return False


def analyze_utilities_services(snapshot: dict[str, Any]) -> dict[str, Any]:
    group = pick_group(snapshot, "UtilitiesServicesSemantics")
    utility = pick_group(snapshot, "UtilityPressureSemantics")
    official = pick_group(snapshot, "OfficialCityStatistics")
    services_block = pick_group(official, "CityServices")
    status = str(pick(group, "Status", "status") or "unavailable")

    electricity_production = _num(pick(group, "ElectricityProduction", "electricity_production"))
    electricity_consumption = _num(pick(group, "ElectricityConsumption", "electricity_consumption"))
    electricity_capacity = _num(pick(group, "ElectricityCapacity", "electricity_capacity"))
    electricity_fulfilled = _num(
        pick(group, "ElectricityFulfilledConsumption", "electricity_fulfilled_consumption")
    )
    electricity_fulfillment = _num(
        pick(group, "ElectricityFulfillmentPercent", "electricity_fulfillment_percent")
    )
    electricity_pressure = str(
        pick(group, "ElectricityPressure", "electricity_pressure") or "unknown"
    )
    garbage_accumulation = _num(pick(group, "GarbageAccumulation", "garbage_accumulation"))
    garbage_processing = _num(pick(group, "GarbageProcessing", "garbage_processing"))
    healthcare_beds_total = _num(pick(group, "HealthcareBedsTotal", "healthcare_beds_total"))
    healthcare_beds_used = _num(pick(group, "HealthcareBedsUsed", "healthcare_beds_used"))

    water = pick_group(utility, "Water")
    sewage = pick_group(utility, "Sewage")
    water_fulfillment = _num(pick(water, "FulfillmentPercent", "fulfillment_percent"))
    water_unfulfilled = _num(pick(water, "UnfulfilledConsumption", "unfulfilled_consumption"))
    water_import = _num(pick(water, "ImportPerMonth", "import_per_month"))
    water_pressure = str(pick(utility, "WaterPressure", "water_pressure") or "unknown")

    sewage_fulfillment = _num(pick(sewage, "FulfillmentPercent", "fulfillment_percent"))
    sewage_unfulfilled = _num(pick(sewage, "UnfulfilledConsumption", "unfulfilled_consumption"))
    sewage_export = _num(pick(sewage, "ExportPerMonth", "export_per_month"))
    sewage_pressure = str(pick(utility, "SewagePressure", "sewage_pressure") or "unknown")

    if electricity_production is None:
        electricity_block = pick_group(utility, "Electricity")
        electricity_production = _num(pick(electricity_block, "Capacity", "capacity"))
        electricity_capacity = electricity_capacity or _num(pick(electricity_block, "Capacity", "capacity"))
        electricity_consumption = electricity_consumption or _num(
            pick(electricity_block, "Consumption", "consumption")
        )
        electricity_fulfilled = electricity_fulfilled or _num(
            pick(electricity_block, "FulfilledConsumption", "fulfilled_consumption")
        )
        electricity_fulfillment = electricity_fulfillment or _num(
            pick(electricity_block, "FulfillmentPercent", "fulfillment_percent")
        )

    city_service_fill = _num(pick(utility, "CityServiceFillPercent", "city_service_fill_percent"))
    if city_service_fill is None:
        workers = _num(pick(services_block, "CityServiceWorkers", "city_service_workers"))
        max_workers = _num(pick(services_block, "CityServiceMaxWorkers", "city_service_max_workers"))
        if workers is not None and max_workers is not None and max_workers > 0:
            city_service_fill = workers * 100.0 / max_workers

    services: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    electricity_detail = _fulfillment_detail(electricity_fulfillment, noun="power")
    if electricity_pressure not in ("ok", "unknown", ""):
        electricity_detail = f"{electricity_detail} · {electricity_pressure.replace('_', ' ')}"
    electricity_severity = "warn" if electricity_pressure in _ELECTRICITY_PRESSURE_WARN else "ok"
    services.append(
        _service_row(
            row_id="electricity",
            label="Power",
            detail=electricity_detail,
            severity=electricity_severity,
        )
    )
    if electricity_pressure in _ELECTRICITY_PRESSURE_WARN:
        parts = [f"Electricity pressure: {electricity_pressure.replace('_', ' ')}"]
        if electricity_fulfillment is not None:
            parts.append(f"fulfillment {electricity_fulfillment:.0f}%")
        if electricity_consumption is not None and electricity_capacity is not None:
            parts.append(f"{int(electricity_consumption)} wanted / {int(electricity_capacity)} capacity")
        findings.append(
            {
                "id": "electricity_pressure",
                "severity": "warn",
                "title": "Electricity shortfall",
                "detail": " · ".join(parts),
                "ask_prompt": "Why is electricity service failing in my city?",
            }
        )

    water_detail = _fulfillment_detail(water_fulfillment, noun="water")
    if water_unfulfilled is not None and water_unfulfilled > 0:
        water_detail = f"{water_detail} · {int(water_unfulfilled)} unfulfilled"
    if water_import is not None and water_import > 0:
        water_detail = f"{water_detail} · importing {int(water_import)}/month"
    water_severity = "warn" if _water_pressure_triggered(utility, water, snapshot) else "ok"
    services.append(
        _service_row(
            row_id="water",
            label="Water",
            detail=water_detail,
            severity=water_severity,
        )
    )
    if water_severity == "warn":
        findings.append(
            {
                "id": "water_pressure",
                "severity": "warn",
                "title": "Water service under pressure",
                "detail": water_detail,
                "ask_prompt": "How do I fix water shortages and pumping capacity?",
            }
        )

    sewage_detail = _fulfillment_detail(sewage_fulfillment, noun="sewage")
    if sewage_unfulfilled is not None and sewage_unfulfilled > 0:
        sewage_detail = f"{sewage_detail} · {int(sewage_unfulfilled)} unfulfilled"
    if sewage_export is not None and sewage_export > 0:
        sewage_detail = f"{sewage_detail} · exporting {int(sewage_export)}/month"
    sewage_severity = "warn" if _sewage_pressure_triggered(utility, sewage, snapshot) else "ok"
    services.append(
        _service_row(
            row_id="sewage",
            label="Sewage",
            detail=sewage_detail,
            severity=sewage_severity,
        )
    )
    if sewage_severity == "warn":
        findings.append(
            {
                "id": "sewage_pressure",
                "severity": "warn",
                "title": "Sewage and treatment under pressure",
                "detail": sewage_detail,
                "ask_prompt": "How do I fix sewage and water treatment in my city?",
            }
        )

    if garbage_accumulation is not None:
        garbage_detail = f"Daily accumulation {int(garbage_accumulation):,}"
        if garbage_processing is not None:
            garbage_detail = f"{garbage_detail} · processing {int(garbage_processing):,}"
        garbage_severity = (
            "warn" if garbage_accumulation >= _GARBAGE_ACCUMULATION_WARN else "ok"
        )
        services.append(
            _service_row(
                row_id="garbage",
                label="Garbage",
                detail=garbage_detail,
                severity=garbage_severity,
            )
        )
        if garbage_accumulation >= _GARBAGE_ACCUMULATION_WARN:
            findings.append(
                {
                    "id": "garbage_accumulation",
                    "severity": "warn",
                    "title": "Garbage backlog rising",
                    "detail": f"Estimated daily garbage accumulation {int(garbage_accumulation):,}.",
                    "ask_prompt": "How do I fix garbage collection and processing?",
                }
            )
    else:
        services.append(
            _service_row(
                row_id="garbage",
                label="Garbage",
                detail="Garbage data unavailable",
            )
        )

    if city_service_fill is not None:
        staffing_detail = f"{city_service_fill:.0f}% staffed"
        staffing_severity = "warn" if city_service_fill < _CITY_SERVICE_FILL_LOW else "ok"
        services.append(
            _service_row(
                row_id="city_services",
                label="City services",
                detail=staffing_detail,
                severity=staffing_severity,
            )
        )
        if city_service_fill < _CITY_SERVICE_FILL_LOW:
            findings.append(
                {
                    "id": "city_services_understaffed",
                    "severity": "warn",
                    "title": "City services understaffed",
                    "detail": f"City service buildings are {city_service_fill:.0f}% staffed.",
                    "ask_prompt": "How do I staff police, fire, health, and education buildings?",
                }
            )
    else:
        services.append(
            _service_row(
                row_id="city_services",
                label="City services",
                detail="Staffing data unavailable",
            )
        )

    if (
        healthcare_beds_total is not None
        and healthcare_beds_used is not None
        and healthcare_beds_total > 0
    ):
        fill = healthcare_beds_used * 100.0 / healthcare_beds_total
        bed_severity = "warn" if fill >= 95 else "ok"
        services.append(
            _service_row(
                row_id="healthcare_beds",
                label="Hospital beds",
                detail=f"{healthcare_beds_used:.0f}/{healthcare_beds_total:.0f} in use ({fill:.0f}%)",
                severity=bed_severity,
            )
        )
        if fill >= 95:
            findings.append(
                {
                    "id": "healthcare_beds_full",
                    "severity": "warn",
                    "title": "Hospital beds nearly full",
                    "detail": f"{healthcare_beds_used:.0f}/{healthcare_beds_total:.0f} beds in use ({fill:.0f}%).",
                    "ask_prompt": "How do I add healthcare capacity?",
                }
            )

    power_headline: str | None = None
    if electricity_fulfillment is not None:
        power_headline = f"{electricity_fulfillment:.0f}% power fulfilled"
    elif electricity_consumption is not None and electricity_capacity is not None:
        power_headline = f"{int(electricity_capacity):,} / {int(electricity_consumption):,} power capacity"

    if findings:
        summary = findings[0]["detail"]
    elif status in ("ok", "partial"):
        summary = power_headline or "Utilities and services metrics are available."
    else:
        summary = "Utilities/services export is unavailable in this snapshot."

    return {
        "ok": status in ("ok", "partial"),
        "status": status,
        "summary": summary,
        "services": services,
        "findings": findings,
        "electricity_production": electricity_production,
        "electricity_consumption": electricity_consumption,
        "electricity_capacity": electricity_capacity,
        "electricity_fulfillment_percent": electricity_fulfillment,
        "electricity_pressure": electricity_pressure,
        "water_fulfillment_percent": water_fulfillment,
        "water_pressure": water_pressure,
        "sewage_fulfillment_percent": sewage_fulfillment,
        "sewage_pressure": sewage_pressure,
        "garbage_accumulation": garbage_accumulation,
        "garbage_processing": garbage_processing,
        "city_service_fill_percent": city_service_fill,
        "healthcare_beds_total": healthcare_beds_total,
        "healthcare_beds_used": healthcare_beds_used,
        "power_headline": power_headline,
        "ask_prompt": (
            "How do I fix water, sewage, electricity, garbage, and city service staffing in my city?"
        ),
    }
