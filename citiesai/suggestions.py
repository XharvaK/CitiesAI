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
    advisor_style: str = "civic",
) -> list[str]:
    suggestions: list[str] = []

    for issue in (metrics or {}).get("city_issues") or []:
        prompt = issue.get("ask_prompt")
        if prompt:
            suggestions.append(_style_suggestion(str(prompt), advisor_style))

    for issue in issues:
        prompt = issue.get("ask_prompt")
        if prompt:
            suggestions.append(_style_suggestion(str(prompt), advisor_style))

    m = metrics or {}
    income = m.get("income")
    expense = m.get("expense")
    if (
        isinstance(income, (int, float))
        and isinstance(expense, (int, float))
        and expense > income
        and expense > 0
    ):
        suggestions.append(
            _style_suggestion(
                "What should I fix in my budget to stop running a deficit?",
                advisor_style,
            )
        )

    wellbeing = m.get("wellbeing")
    if isinstance(wellbeing, (int, float)) and wellbeing < 50:
        suggestions.append(
            _style_suggestion("What is hurting wellbeing in my city?", advisor_style)
        )

    health = m.get("health")
    if isinstance(health, (int, float)) and health < 50:
        suggestions.append(
            _style_suggestion(
                "Do I need more clinics or hospitals for my citizens?",
                advisor_style,
            )
        )

    congestion = m.get("congestion_percent")
    lines = m.get("transit_lines") or 0
    if isinstance(congestion, (int, float)) and congestion > 50 and not lines:
        suggestions.append(
            _style_suggestion(
                "Should I add bus or rail lines to reduce traffic?",
                advisor_style,
            )
        )

    if isinstance(congestion, (int, float)) and congestion > 50:
        suggestions.append(
            _style_suggestion(
                "How can I reduce traffic congestion in my city?",
                advisor_style,
            )
        )

    unemployment = m.get("unemployment_percent")
    if isinstance(unemployment, (int, float)) and unemployment > 15:
        suggestions.append(
            _style_suggestion(
                "How can I reduce unemployment in my city?",
                advisor_style,
            )
        )

    suggestions.extend(_style_suggestion(item, advisor_style) for item in FALLBACK_SUGGESTIONS)
    return _unique(suggestions, limit=max_suggestions)


def _style_suggestion(prompt: str, advisor_style: str) -> str:
    style = str(advisor_style or "civic").strip().lower()
    text = prompt.strip()
    if style == "conversational":
        if text.endswith("?"):
            return text
        return f"{text}?"
    if style == "analyst":
        if "metric" in text.lower() or "which" in text.lower():
            return text
        return text.replace("How can I", "Which metrics explain how to").replace(
            "What should I", "Which measured factors should guide what I"
        )
    return text
