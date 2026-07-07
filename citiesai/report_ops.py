"""Report card build + historian persistence."""

from __future__ import annotations

from typing import Any

from .analyzers import build_report_card
from .city_name import resolve_city_display_name
from .constants import HISTORY_MAX_POINTS
from .historian import CityHistorian, get_historian
from .snapshot import SnapshotMeta


def build_and_persist_report_card(
    snapshot: dict[str, Any],
    meta: SnapshotMeta,
    *,
    historian: CityHistorian | None = None,
    headline_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hist = historian or get_historian()
    export_path = meta.path
    hist.sync(export_path, force=False)
    city_name = resolve_city_display_name(snapshot, meta)
    history = hist.get_history(city_name, export_path=export_path, limit=HISTORY_MAX_POINTS)
    prev_scores = hist.previous_session_report_scores(city_name, history=history)
    treasury_series = history.get("series", {}).get("treasury")
    card = build_report_card(
        snapshot,
        meta,
        previous_domain_scores=prev_scores,
        treasury_series=treasury_series,
        headline_metrics=headline_metrics,
    )
    exported_at = meta.exported_at_utc
    if exported_at and card.get("domain_scores"):
        existing = hist.report_scores_at(city_name, exported_at)
        if existing != card["domain_scores"]:
            hist.save_report_scores(city_name, exported_at, card["domain_scores"])
    return card
