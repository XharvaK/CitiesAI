"""Trend forecasts from session or historian data."""

from __future__ import annotations

from typing import Any


def _linear_forecast(values: list[float], steps: int = 6) -> list[float | None]:
    """Project `steps` points ahead using simple linear regression."""
    if len(values) < 3:
        return [None] * steps
    n = len(values)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return [values[-1]] * steps
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=True)) / denom
    intercept = y_mean - slope * x_mean
    return [intercept + slope * (n + i) for i in range(steps)]


def build_forecasts(history: dict[str, Any], *, horizon: int = 6) -> dict[str, Any]:
    series = history.get("series") or {}
    forecasts: dict[str, Any] = {}
    for key in ("treasury", "population", "wellbeing", "health"):
        raw = series.get(key) or []
        values = [float(v) for v in raw if isinstance(v, (int, float))]
        if len(values) < 3:
            continue
        projected = _linear_forecast(values, steps=horizon)
        forecasts[key] = {
            "current": values[-1],
            "projected": projected,
            "delta_to_end": (projected[-1] - values[-1]) if projected[-1] is not None else None,
        }

    alerts: list[str] = []
    treasury = forecasts.get("treasury")
    if treasury and treasury.get("projected"):
        end = treasury["projected"][-1]
        if isinstance(end, (int, float)) and end < 0:
            alerts.append("Treasury may go negative at current trend.")
        elif isinstance(end, (int, float)) and isinstance(treasury["current"], (int, float)):
            if end < treasury["current"] * 0.5:
                alerts.append("Treasury trending down sharply.")

    rate_series = series.get("treasury_net_per_hour") or []
    hourly_net = rate_series[-1] if rate_series else None
    if isinstance(hourly_net, (int, float)) and hourly_net < 0:
        current_treasury = series.get("treasury")
        if isinstance(current_treasury, list) and current_treasury:
            last = current_treasury[-1]
            if isinstance(last, (int, float)) and hourly_net != 0:
                hours_to_zero = last / abs(hourly_net)
                if 0 < hours_to_zero <= 4:
                    alerts.append(f"Treasury may hit zero in ~{hours_to_zero:.1f} hours at current burn.")

    return {"forecasts": forecasts, "alerts": alerts, "horizon_points": horizon}
