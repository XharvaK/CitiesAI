"""Housing and labor market balance auditor."""

from __future__ import annotations

from typing import Any

from ..snapshot import pick, pick_group


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def analyze_housing_labor(snapshot: dict[str, Any]) -> dict[str, Any]:
    housing = pick_group(snapshot, "HousingPressureSemantics")
    labor = pick_group(snapshot, "LaborPressureContext")
    labor_detail = pick_group(snapshot, "LaborMarketDetail")
    workforce = pick_group(snapshot, "Workforce")
    workplaces = pick_group(snapshot, "Workplaces")

    findings: list[dict[str, str]] = []

    households = _num(pick(housing, "HouseholdCount", "household_count"))
    residential = _num(pick(housing, "ResidentialBuildingCount", "residential_building_count"))
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
    workers = _num(pick(labor, "TotalWorkers", "total_workers"))
    outside = _num(pick(labor, "OutsideWorkersSharePercent", "outside_workers_share_percent"))
    underemployed = _num(pick(labor, "UnderemployedSharePercent", "underemployed_share_percent"))

    unemployed = _num(pick(workforce, "UnemployedWorkers", "unemployed_workers"))
    open_jobs = _num(pick(workplaces, "OpenWorkplaces", "open_workplaces"))

    if jobs is not None and workers is not None:
        gap = jobs - workers
        if gap > 500:
            findings.append(
                {
                    "id": "jobs_gap",
                    "severity": "warn",
                    "title": "More jobs than local workers",
                    "detail": f"{int(gap):,} more jobs than workers — commuters may be filling roles.",
                    "action": "Grow population or zone more residential near industry.",
                }
            )
        elif gap < -500:
            findings.append(
                {
                    "id": "worker_surplus",
                    "severity": "info",
                    "title": "Worker surplus",
                    "detail": f"{int(-gap):,} more workers than jobs.",
                    "action": "Zone commercial/office/industrial for local employment.",
                }
            )

    if unemployed is not None and unemployed >= 20:
        findings.append(
            {
                "id": "unemployment",
                "severity": "warn",
                "title": "Unemployed workers",
                "detail": f"{int(unemployed):,} unemployed workers.",
                "action": "Add workplaces matching education levels.",
            }
        )

    if open_jobs is not None and open_jobs > 100:
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

    education_levels = pick(labor_detail, "Levels", "levels")
    if isinstance(education_levels, list):
        for level in education_levels:
            if not isinstance(level, dict):
                continue
            level_name = str(pick(level, "Level", "level") or "unknown")
            jobs_lvl = _num(pick(level, "Jobs", "jobs"))
            workers_lvl = _num(pick(level, "Workers", "workers"))
            if jobs_lvl is not None and workers_lvl is not None and jobs_lvl > workers_lvl * 1.5:
                findings.append(
                    {
                        "id": f"edu_gap_{level_name}",
                        "severity": "info",
                        "title": f"Jobs gap ({level_name})",
                        "detail": f"{int(jobs_lvl):,} jobs vs {int(workers_lvl):,} {level_name} workers.",
                        "action": f"Train more {level_name} workers or adjust zoning.",
                    }
                )

    return {
        "finding_count": len(findings),
        "findings": findings,
        "summary": (
            f"{len(findings)} housing/labor findings."
            if findings
            else "Housing and labor look balanced."
        ),
    }
