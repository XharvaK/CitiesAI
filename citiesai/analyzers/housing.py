"""Housing and labor market balance auditor."""

from __future__ import annotations

from typing import Any

from ..snapshot import pick, pick_group

_LEVEL_LABELS = {
    0: "untrained",
    1: "poorly educated",
    2: "educated",
    3: "well educated",
    4: "highly educated",
}


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def _level_value(group: Any, level: int) -> float | int | None:
    if not isinstance(group, dict):
        return None
    key = f"level_{level}"
    return _num(pick(group, f"Level{level}", key))


def _education_level_findings(labor_detail: dict[str, Any]) -> list[dict[str, str]]:
    jobs_open = pick(labor_detail, "JobsOpenByEducationLevel", "jobs_open_by_education_level")
    workforce_edu = pick(labor_detail, "WorkforceByEducationLevel", "workforce_by_education_level")
    workers_group: dict[str, Any] | None = None
    if isinstance(workforce_edu, dict):
        workers_group = pick(workforce_edu, "Workers", "workers")
        if not isinstance(workers_group, dict):
            workers_group = None

    findings: list[dict[str, str]] = []
    if not isinstance(jobs_open, dict):
        return findings

    for level in range(5):
        open_jobs = _level_value(jobs_open, level)
        worker_count = _level_value(workers_group, level) if workers_group else None
        if open_jobs is None or open_jobs <= 50:
            continue
        if worker_count is not None and open_jobs <= worker_count * 0.5:
            continue
        label = _LEVEL_LABELS.get(level, f"level {level}")
        detail = f"{int(open_jobs):,} open jobs at {label} level."
        if worker_count is not None:
            detail = (
                f"{int(open_jobs):,} open jobs vs {int(worker_count):,} "
                f"{label} workers."
            )
        findings.append(
            {
                "id": f"edu_gap_level_{level}",
                "severity": "info",
                "title": f"Jobs gap ({label})",
                "detail": detail,
                "action": f"Train more {label} workers or adjust zoning.",
            }
        )
    return findings


def analyze_housing_labor(snapshot: dict[str, Any]) -> dict[str, Any]:
    housing = pick_group(snapshot, "HousingPressureSemantics")
    labor = pick_group(snapshot, "LaborPressureContext")
    labor_detail = pick_group(snapshot, "LaborMarketDetail")
    workforce = pick_group(snapshot, "Workforce")
    workplaces = pick_group(snapshot, "Workplaces")

    findings: list[dict[str, str]] = []

    households = _num(
        pick(
            housing,
            "TotalHouseholds",
            "total_households",
            "HouseholdCount",
            "household_count",
        )
    )
    residential = _num(
        pick(
            housing,
            "ResidentialBuildingEntities",
            "residential_building_entities",
            "ResidentialBuildingCount",
            "residential_building_count",
        )
    )
    homeless_hh = _num(pick(housing, "HomelessHouseholds", "homeless_households"))
    moving_hh = _num(pick(housing, "MovingAwayHouseholds", "moving_away_households"))

    if households is not None and residential is not None and residential > 0:
        ratio = households / residential
        if ratio > 1.05:
            findings.append(
                {
                    "id": "housing_shortage",
                    "severity": "warn",
                    "title": "Housing shortage",
                    "detail": (
                        f"{int(households):,} households vs {int(residential):,} residential buildings "
                        f"({ratio:.2f} households/building)."
                    ),
                    "action": "Zone more residential — medium density first if land is tight.",
                }
            )

    if homeless_hh is not None and homeless_hh > 0:
        findings.append(
            {
                "id": "homeless_households",
                "severity": "warn",
                "title": "Homeless households",
                "detail": f"{int(homeless_hh):,} households without homes.",
                "action": "Add housing and check service coverage in growth areas.",
            }
        )

    if moving_hh is not None and moving_hh > 0:
        findings.append(
            {
                "id": "moving_away",
                "severity": "info",
                "title": "Households leaving",
                "detail": f"{int(moving_hh):,} households moving away.",
                "action": "Check taxes, noise, pollution, and job access.",
            }
        )

    jobs = _num(pick(labor, "TotalJobs", "total_jobs"))
    workers = _num(
        pick(
            labor,
            "TotalPotentialWorkers",
            "total_potential_workers",
            "TotalWorkers",
            "total_workers",
        )
    )
    jobs_gap = _num(pick(labor, "JobsMinusCurrentWorkers", "jobs_minus_current_workers"))
    outside = _num(
        pick(
            labor,
            "OutsideWorkerSharePercent",
            "outside_worker_share_percent",
            "OutsideWorkersSharePercent",
            "outside_workers_share_percent",
        )
    )
    underemployed = _num(
        pick(
            labor,
            "UnderemployedWorkerSharePercent",
            "underemployed_worker_share_percent",
            "UnderemployedSharePercent",
            "underemployed_share_percent",
        )
    )

    unemployed = _num(
        pick(workforce, "Unemployed", "unemployed", "UnemployedWorkers", "unemployed_workers")
    )
    open_jobs = _num(pick(workplaces, "OpenWorkplaces", "open_workplaces"))

    gap: float | int | None
    if jobs_gap is not None:
        gap = jobs_gap
    elif jobs is not None and workers is not None:
        gap = jobs - workers
    else:
        gap = None

    gap_threshold = 500
    if workers is not None and workers > 0:
        gap_threshold = max(50, int(workers * 0.05))

    if gap is not None:
        if gap > gap_threshold:
            findings.append(
                {
                    "id": "jobs_gap",
                    "severity": "warn",
                    "title": "More jobs than local workers",
                    "detail": (
                        f"{int(gap):,} more jobs than workers — "
                        "commuters may be filling roles."
                    ),
                    "action": "Grow population or zone more residential near industry.",
                }
            )
        elif gap < -gap_threshold:
            findings.append(
                {
                    "id": "worker_surplus",
                    "severity": "info",
                    "title": "Worker surplus",
                    "detail": f"{int(-gap):,} more workers than jobs.",
                    "action": "Zone commercial/office/industrial for local employment.",
                }
            )

    unemployed_threshold = 20
    if workers is not None and workers > 0:
        unemployed_threshold = max(5, int(workers * 0.01))

    if unemployed is not None and unemployed >= unemployed_threshold:
        findings.append(
            {
                "id": "unemployment",
                "severity": "warn",
                "title": "Unemployed workers",
                "detail": f"{int(unemployed):,} unemployed workers.",
                "action": "Add workplaces matching education levels.",
            }
        )

    open_jobs_threshold = 100
    if jobs is not None and jobs > 0:
        open_jobs_threshold = max(20, int(jobs * 0.05))

    if open_jobs is not None and open_jobs > open_jobs_threshold:
        findings.append(
            {
                "id": "open_jobs",
                "severity": "info",
                "title": "Unfilled jobs",
                "detail": f"{int(open_jobs):,} open workplaces.",
                "action": "Check education mismatch or worker commute access.",
            }
        )

    if outside is not None and outside > 25:
        findings.append(
            {
                "id": "outside_workers",
                "severity": "info",
                "title": "Outside workers",
                "detail": f"{outside:.0f}% of workers commute from outside the city.",
                "action": "Balance jobs and housing locally.",
            }
        )

    if underemployed is not None and underemployed > 15:
        findings.append(
            {
                "id": "underemployed",
                "severity": "info",
                "title": "Underemployed workers",
                "detail": f"{underemployed:.0f}% underemployed.",
                "action": "Add higher-education jobs or improve schools.",
            }
        )

    findings.extend(_education_level_findings(labor_detail))

    return {
        "finding_count": len(findings),
        "findings": findings,
        "summary": (
            f"{len(findings)} housing/labor findings."
            if findings
            else "Housing and labor look balanced."
        ),
    }
