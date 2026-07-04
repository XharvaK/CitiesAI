from __future__ import annotations

from typing import Any

FALLBACK_SUGGESTIONS = [
    "What should I prioritize next given my budget?",
    "Why is residential demand low?",
    "Do I need more schools or clinics?",
    "Should I add bus lines given current traffic?",
    "What is hurting wellbeing or health?",
]


def _unique(items: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
        if len(out) >= limit:
            break
    return out


def build_ask_suggestions(
    issues: list[dict[str, Any]],
    metrics: dict[str, Any] | None = None,
    *,
    max_suggestions: int = 5,
) -> list[str]:
    suggestions: list[str] = []

    for issue in (metrics or {}).get("city_issues") or []:
        prompt = issue.get("ask_prompt")
        if prompt:
            suggestions.append(str(prompt))

    for issue in issues:
        prompt = issue.get("ask_prompt")
        if prompt:
            suggestions.append(str(prompt))

    m = metrics or {}
    income = m.get("income")
    expense = m.get("expense")
    if (
        isinstance(income, (int, float))
        and isinstance(expense, (int, float))
        and expense > income
        and expense > 0
    ):
        suggestions.append("What should I fix in my budget to stop running a deficit?")

    wellbeing = m.get("wellbeing")
    if isinstance(wellbeing, (int, float)) and wellbeing < 50:
        suggestions.append("What is hurting wellbeing in my city?")

    health = m.get("health")
    if isinstance(health, (int, float)) and health < 50:
        suggestions.append("Do I need more clinics or hospitals for my citizens?")

    traffic = m.get("traffic_volume")
    lines = m.get("transit_lines") or 0
    if isinstance(traffic, (int, float)) and traffic > 40 and not lines:
        suggestions.append("Should I add bus or rail lines to reduce traffic?")

    employment = m.get("employment_percent")
    if isinstance(employment, (int, float)) and employment < 85:
        suggestions.append("How can I reduce unemployment in my city?")

    suggestions.extend(FALLBACK_SUGGESTIONS)
    return _unique(suggestions, limit=max_suggestions)
