from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def social_index(raw: Any, level: Any = None) -> float | None:
    """Map official social Health/Wellbeing export fields to a 0–100 index."""
    raw_n = _num(raw)
    if raw_n is not None:
        if 0 <= raw_n <= 100:
            return float(raw_n)
        scaled = raw_n / 1000.0
        if 0 <= scaled <= 100:
            return scaled

    level_n = _num(level)
    if level_n is not None and 1 <= level_n <= 5:
        return level_n * 20.0

    return None


def format_social_index(index: float | int | None) -> str:
    if index is None:
        return "n/a"
    return f"{index:.1f}"
