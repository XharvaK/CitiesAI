"""Exported civic briefing HTML contracts."""

from __future__ import annotations

from pathlib import Path

from citiesai.report_html import render_report_html
from citiesai.snapshot import load_snapshot, snapshot_meta

VENDOR_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "vendor/Cities2-DataExport/sample/latest.sample.json"
)


def test_report_html_is_dark_civic_briefing() -> None:
    snapshot = load_snapshot(VENDOR_SAMPLE)
    meta = snapshot_meta(snapshot, path=VENDOR_SAMPLE)
    html = render_report_html(snapshot, meta)
    assert "color-scheme: dark" in html
    assert "Civic briefing" in html
    assert "Priorities" in html
    assert "Report card" in html
    assert "Appendix · Economy" in html
    assert "Appendix · Housing" in html
    assert "Appendix · Transit" in html
    assert "#f4f6fb" not in html
    assert "Resolved history" not in html
    assert "print-color-adjust: exact" in html
