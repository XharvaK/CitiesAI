from __future__ import annotations

import re
from collections.abc import Iterable

from .snapshot import pick, pick_group
from .social_stats import resident_population, social_index

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "what",
    "when",
    "why",
    "with",
    "city",
    "cities",
    "skylines",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [token for token in tokens if len(token) > 2 and token not in STOPWORDS]


def _unique(terms: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(term)
    return ordered


def _token_set(*parts: str) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        tokens.update(_tokenize(part))
    return tokens


def snapshot_signals(snapshot: dict) -> list[str]:
    terms: list[str] = []
    population = pick_group(snapshot, "Population")
    official = pick_group(snapshot, "OfficialCityStatistics")
    finance = pick_group(official, "Finance")
    social = pick_group(official, "Social")
    education = pick_group(snapshot, "Education")
    transport = pick_group(snapshot, "TransportProxies")
    mobility = pick_group(snapshot, "Mobility")
    workforce = pick_group(snapshot, "Workforce")

    total_pop = pick(population, "TotalPopulation", "total_population") or 0
    has_citizens = bool(total_pop)

    homeless = pick(population, "HomelessPopulation", "homeless_population") or 0
    moving_away = pick(population, "MovingAwayPopulation", "moving_away_population") or 0
    if homeless:
        terms.extend(["homeless", "housing", "residential", "demand", "welfare"])
    if moving_away:
        terms.extend(["moving away", "happiness", "wellbeing", "services", "pollution"])

    income = pick(finance, "Income", "income") or 0
    expense = pick(finance, "Expense", "expense") or 0
    if expense > income and expense > 0:
        terms.extend(["budget", "finance", "taxation", "expenses", "income", "loans"])

    residents = resident_population(snapshot)

    wellbeing = social_index(
        pick(social, "Wellbeing", "wellbeing"),
        population=residents,
    )
    health = social_index(
        pick(social, "Health", "health"),
        population=residents,
    )
    crime_rate = pick(social, "CrimeRate", "crime_rate") or 0
    if has_citizens and isinstance(wellbeing, (int, float)) and wellbeing < 50:
        terms.extend(["wellbeing", "happiness", "services", "noise", "pollution"])
    if has_citizens and isinstance(health, (int, float)) and health < 50:
        terms.extend(["health", "healthcare", "hospital", "clinic", "pollution"])
    if crime_rate:
        terms.extend(["crime", "police", "safety"])

    employment = pick(education, "EmploymentRatePercent", "employment_rate_percent")
    if has_citizens and isinstance(employment, (int, float)) and employment < 85:
        terms.extend(["unemployment", "jobs", "workplace", "education", "office demand"])

    congestion = pick(transport, "CongestionIndex0To1", "congestion_index_0_to_1")
    if isinstance(congestion, (int, float)) and congestion > 0.5:
        terms.extend(["traffic", "congestion", "roads", "public transportation"])

    lines_total = pick(mobility, "LinesTotal", "lines_total") or 0
    traffic_volume = pick(mobility, "TrafficVolumeIndex", "traffic_volume_index") or 0
    if has_citizens and traffic_volume and not lines_total:
        terms.extend(["public transportation", "bus", "subway", "transit", "passengers"])

    unemployed = pick(workforce, "UnemployedWorkers", "unemployed_workers") or 0
    if unemployed:
        terms.extend(["unemployment", "jobs", "zoning", "industrial", "office", "commercial"])

    return _unique(terms)


def _unavailable_groups(snapshot: dict) -> set[str]:
    meta = pick_group(snapshot, "Meta")
    status_map = pick(meta, "MetricStatus", "metric_status")
    if not isinstance(status_map, dict):
        return set()
    return {str(key).lower() for key, value in status_map.items() if str(value).lower() == "unavailable"}


def build_search_queries(snapshot: dict, question: str | None = None, *, max_queries: int = 4) -> list[str]:
    question_terms = _tokenize(question or "")
    signal_terms = snapshot_signals(snapshot)
    unavailable = _unavailable_groups(snapshot)

    queries: list[str] = []
    if question_terms:
        queries.append(" ".join(question_terms[:10]))
    if signal_terms:
        filtered_signals = list(signal_terms)
        if "transport_proxies" in unavailable and "congestion" in filtered_signals:
            filtered_signals = [t for t in filtered_signals if t not in ("congestion", "traffic")]
        queries.append(" ".join(filtered_signals[:10]))
    if question_terms and signal_terms:
        merged = _unique([*question_terms[:6], *signal_terms[:6]])
        queries.append(" ".join(merged[:12]))

    topic_map = {
        "budget": "budget finance taxation expenses income loans",
        "traffic": "traffic congestion roads intersections public transportation",
        "transit": "public transportation subway bus tram passengers stops",
        "housing": "housing demand residential zoning homelessness",
        "education": "education schools university employment jobs",
        "pollution": "pollution environment water noise air",
        "crime": "crime police safety security",
        "tourism": "tourism attractiveness hotels landmarks",
        "industry": "industry zoning processing specialized industry",
        "office": "office demand jobs companies workplace",
        "first": "beginner guide roads water power sewage zoning",
        "new": "beginner guide roads water power sewage zoning",
        "start": "beginner guide roads water power sewage zoning",
    }
    haystack_tokens = _token_set(question or "", " ".join(signal_terms))
    for keyword, query in topic_map.items():
        if keyword in haystack_tokens:
            queries.append(query)

    deduped = _unique(queries)
    return deduped[:max_queries]
