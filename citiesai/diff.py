"""Compare two city export snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .city_name import resolve_city_display_name
from .dashboard import extract_headline_metrics
from .snapshot import snapshot_meta

_DIFF_KEYS = (
    ("population", "Population"),
    ("treasury", "Treasury"),
    ("income", "Income"),
    ("expense", "Expense"),
    ("wellbeing", "Wellbeing"),
    ("health", "Health"),
    ("homeless", "Homeless"),
    ("moving_away", "Moving away"),
    ("employment_percent", "Employment %"),
    ("traffic_volume", "Traffic volume"),
    ("transit_lines", "Transit lines"),
    ("crime_rate", "Crime rate"),
)


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def diff_snapshots(
    snapshot_a: dict[str, Any],
    snapshot_b: dict[str, Any],
    *,
    path_a: Path | None = None,
    path_b: Path | None = None,
) -> dict[str, Any]:
    meta_a = snapshot_meta(snapshot_a, path=path_a or Path("a.json"))
    meta_b = snapshot_meta(snapshot_b, path=path_b or Path("b.json"))
    metrics_a = extract_headline_metrics(snapshot_a, meta_a)
    metrics_b = extract_headline_metrics(snapshot_b, meta_b)

    changes: list[dict[str, Any]] = []
    for key, label in _DIFF_KEYS:
        a = _num(metrics_a.get(key))
        b = _num(metrics_b.get(key))
        if a is None and b is None:
            continue
        delta = None
        if a is not None and b is not None:
            delta = b - a
        changes.append(
            {
                "key": key,
                "label": label,
                "before": a,
                "after": b,
                "delta": delta,
            }
        )

    return {
        "city_a": resolve_city_display_name(snapshot_a, meta_a),
        "city_b": resolve_city_display_name(snapshot_b, meta_b),
        "exported_at_a": meta_a.exported_at_utc,
        "exported_at_b": meta_b.exported_at_utc,
        "game_time_a": f"Y{metrics_a.get('game_year')} M{metrics_a.get('game_month')}",
        "game_time_b": f"Y{metrics_b.get('game_year')} M{metrics_b.get('game_month')}",
        "changes": changes,
    }


def format_diff_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Snapshot diff: {result['city_a']} → {result['city_b']}",
        "",
        f"- **Before:** {result['exported_at_a']} ({result['game_time_a']})",
        f"- **After:** {result['exported_at_b']} ({result['game_time_b']})",
        "",
        "| Metric | Before | After | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in result["changes"]:
        before = row["before"]
        after = row["after"]
        delta = row["delta"]
        fmt_before = f"{before:,.1f}" if isinstance(before, float) else f"{before:,}" if before is not None else "n/a"
        fmt_after = f"{after:,.1f}" if isinstance(after, float) else f"{after:,}" if after is not None else "n/a"
        if delta is None:
            fmt_delta = "n/a"
        elif isinstance(delta, float):
            fmt_delta = f"{delta:+,.1f}"
        else:
            fmt_delta = f"{delta:+,}"
        lines.append(f"| {row['label']} | {fmt_before} | {fmt_after} | {fmt_delta} |")
    return "\n".join(lines)


def resolve_snapshot_path(ref: str, *, export_dir: Path) -> Path:
    path = Path(ref).expanduser()
    if path.is_file():
        return path
    snap_dir = export_dir / "snapshots"
    candidate = snap_dir / ref
    if candidate.is_file():
        return candidate
    if not ref.endswith(".json"):
        candidate = snap_dir / f"{ref}.json"
        if candidate.is_file():
            return candidate
    if ref == "latest":
        latest = export_dir / "latest.json"
        if latest.is_file():
            return latest
    raise FileNotFoundError(f"Snapshot not found: {ref}")
