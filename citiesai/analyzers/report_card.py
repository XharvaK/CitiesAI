"""City Report Card — letter grades per domain with deltas."""

from __future__ import annotations

from typing import Any

from ..dashboard import extract_headline_metrics
from ..snapshot import SnapshotMeta, pick, pick_group
from .budget import analyze_budget
from .housing import analyze_housing_labor
from .transit import analyze_transit_lines


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _score_clamp(value: float, *, low: float, high: float) -> float:
    if high <= low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def _economy_runway_months(
    treasury: float,
    expense: float,
    *,
    net_monthly: float | None,
    projection_months: int = 12,
) -> float:
    """Months of expenses treasury covers; surplus cities get a forward look."""
    static = treasury / expense
    if net_monthly is not None and net_monthly > 0 and projection_months > 0:
        projected = (treasury + net_monthly * projection_months) / expense
        return max(static, projected)
    return static


def _treasury_momentum_bonus(treasury_series: list[Any] | None) -> float:
    if not treasury_series:
        return 0.0
    values = [float(v) for v in treasury_series if isinstance(v, (int, float))]
    if len(values) < 3:
        return 0.0
    window = values[-10:]
    if len(window) < 3:
        return 0.0
    delta = window[-1] - window[0]
    base = abs(window[0])
    if base <= 0 or delta <= 0:
        return 0.0
    return min(10.0, (delta / base) * 100.0)


def _score_economy(
    *,
    income: Any,
    expense: Any,
    treasury: Any,
    net_monthly: Any,
    treasury_series: list[Any] | None = None,
) -> float:
    margin_score: float | None = None
    runway_score: float | None = None
    margin: float | None = None

    if isinstance(income, (int, float)) and isinstance(expense, (int, float)) and expense > 0:
        margin = (float(income) - float(expense)) / float(expense)
        margin_score = _score_clamp(margin, low=-0.2, high=0.3)

    if isinstance(treasury, (int, float)) and isinstance(expense, (int, float)) and expense > 0:
        net = float(net_monthly) if isinstance(net_monthly, (int, float)) else None
        runway = _economy_runway_months(
            float(treasury),
            float(expense),
            net_monthly=net,
        )
        runway_score = _score_clamp(runway, low=1, high=12)

    if margin_score is not None and runway_score is not None:
        surplus = isinstance(net_monthly, (int, float)) and float(net_monthly) > 0
        if surplus:
            econ_score = margin_score * 0.65 + runway_score * 0.35
        else:
            econ_score = (margin_score + runway_score) / 2
    elif margin_score is not None:
        econ_score = margin_score
    elif runway_score is not None:
        econ_score = runway_score
    else:
        econ_score = 50.0

    econ_score += _treasury_momentum_bonus(treasury_series)
    econ_score = min(100.0, econ_score)

    if margin is not None and isinstance(net_monthly, (int, float)) and float(net_monthly) > 0:
        if margin >= 0.30:
            econ_score = max(econ_score, 80.0)
        elif margin >= 0.15:
            econ_score = max(econ_score, 75.0)

    return econ_score


def _delta_grade(current: str, previous: str | None) -> str | None:
    if not previous or previous == current or current == "N/A" or previous == "N/A":
        return None
    order = ["F", "D", "C", "B", "A"]
    try:
        return f"{previous}→{current}" if order.index(current) != order.index(previous) else None
    except ValueError:
        return None


def build_report_card(
    snapshot: dict[str, Any],
    meta: SnapshotMeta,
    *,
    previous_domain_scores: dict[str, dict[str, Any]] | None = None,
    treasury_series: list[Any] | None = None,
) -> dict[str, Any]:
    metrics = extract_headline_metrics(snapshot, meta)
    budget = analyze_budget(snapshot)
    housing = analyze_housing_labor(snapshot)
    transit = analyze_transit_lines(snapshot)

    official = pick_group(snapshot, "OfficialCityStatistics")
    social = pick_group(official, "Social")
    utility = pick_group(snapshot, "UtilityPressureSemantics")
    city_service_fill = pick(utility, "CityServiceFillPercent", "city_service_fill_percent")

    domains: list[dict[str, Any]] = []

    income = budget.get("income")
    expense = budget.get("expense")
    treasury = budget.get("treasury")
    net_monthly = budget.get("net_monthly")
    econ_score = _score_economy(
        income=income,
        expense=expense,
        treasury=treasury,
        net_monthly=net_monthly,
        treasury_series=treasury_series,
    )
    econ_grade = _grade(econ_score)
    domains.append(
        {
            "id": "economy",
            "label": "Economy",
            "score": round(econ_score, 1),
            "grade": econ_grade,
            "detail": budget.get("summary", ""),
            "ask_prompt": "How can I improve my city budget and economy?",
        }
    )

    transit_lines = transit.get("lines") or []
    line_count = int(transit.get("line_count") or len(transit_lines))
    if not transit.get("ok") or line_count == 0:
        domains.append(
            {
                "id": "transit",
                "label": "Transit",
                "score": None,
                "grade": "N/A",
                "detail": transit.get("summary", ""),
                "ask_prompt": (
                    "How can I build public transit in my city?"
                    if line_count == 0
                    else "How does public transit work in Cities: Skylines II?"
                ),
            }
        )
    else:
        problem = transit.get("problem_count", 0)
        transit_score = max(20.0, 100.0 - problem / line_count * 60)
        total_waiting = transit.get("total_waiting", 0)
        if total_waiting > 500:
            transit_score -= 15
        transit_grade = _grade(transit_score)
        domains.append(
            {
                "id": "transit",
                "label": "Transit",
                "score": round(transit_score, 1),
                "grade": transit_grade,
                "detail": transit.get("summary", ""),
                "ask_prompt": "How can I improve public transit in my city?",
            }
        )

    housing_score = 85.0
    for finding in housing.get("findings", []):
        if finding.get("severity") == "warn":
            housing_score -= 15
        elif finding.get("severity") == "info":
            housing_score -= 5
    homeless = metrics.get("homeless")
    if isinstance(homeless, (int, float)) and homeless > 100:
        housing_score -= min(30, homeless / 50)
    housing_grade = _grade(max(0, housing_score))
    domains.append(
        {
            "id": "housing",
            "label": "Housing & jobs",
            "score": round(max(0, housing_score), 1),
            "grade": housing_grade,
            "detail": housing.get("summary", ""),
            "ask_prompt": "How do I fix housing and jobs balance?",
        }
    )

    services_score = 75.0
    if isinstance(city_service_fill, (int, float)):
        services_score = _score_clamp(city_service_fill, low=50, high=100)
    water_pressure = str(pick(utility, "WaterPressure", "water_pressure") or "")
    sewage_pressure = str(pick(utility, "SewagePressure", "sewage_pressure") or "")
    if water_pressure not in ("ok", "unknown", ""):
        services_score -= 20
    if sewage_pressure not in ("ok", "unknown", ""):
        services_score -= 15
    services_grade = _grade(max(0, services_score))
    domains.append(
        {
            "id": "services",
            "label": "Services",
            "score": round(max(0, services_score), 1),
            "grade": services_grade,
            "detail": (
                f"City service fill {city_service_fill:.0f}%."
                if city_service_fill
                else "Utility/service data partial."
            ),
            "ask_prompt": "What city services should I expand?",
        }
    )

    wellbeing = metrics.get("wellbeing")
    health = metrics.get("health")
    crime = pick(social, "CrimeRate", "crime_rate")
    wellbeing_score = 0.0
    parts = 0
    if isinstance(wellbeing, (int, float)):
        wellbeing_score += _score_clamp(wellbeing, low=40, high=90)
        parts += 1
    if isinstance(health, (int, float)):
        wellbeing_score += _score_clamp(health, low=40, high=90)
        parts += 1
    if isinstance(crime, (int, float)):
        wellbeing_score += 100.0 - _score_clamp(crime, low=0, high=30)
        parts += 1
    if parts:
        wellbeing_score /= parts
    else:
        wellbeing_score = 50.0
    wellbeing_grade = _grade(wellbeing_score)
    domains.append(
        {
            "id": "wellbeing",
            "label": "Wellbeing",
            "score": round(wellbeing_score, 1),
            "grade": wellbeing_grade,
            "detail": (
                f"Wellbeing {wellbeing:.0f}, health {health:.0f}."
                if isinstance(wellbeing, (int, float)) and isinstance(health, (int, float))
                else "Social metrics available."
            ),
            "ask_prompt": "Why is wellbeing low and what should I fix?",
        }
    )

    if previous_domain_scores:
        for domain in domains:
            prev = previous_domain_scores.get(domain["id"])
            if prev and prev.get("grade"):
                domain["grade_delta"] = _delta_grade(domain["grade"], str(prev["grade"]))

    scored = [d for d in domains if d["score"] is not None]
    overall = sum(d["score"] for d in scored) / len(scored) if scored else 50.0
    overall_grade = _grade(overall)

    domain_scores = {
        d["id"]: {"score": d["score"], "grade": d["grade"]}
        for d in domains
    }

    return {
        "overall_grade": overall_grade,
        "overall_score": round(overall, 1),
        "domains": domains,
        "domain_scores": domain_scores,
        "city_name": metrics.get("city_name"),
        "exported_at_utc": meta.exported_at_utc,
    }
