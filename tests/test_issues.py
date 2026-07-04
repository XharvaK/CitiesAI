from __future__ import annotations

from pathlib import Path

import pytest

from citiesai.dashboard import extract_headline_metrics
from citiesai.gui.api import api_issues, api_suggestions
from citiesai.issues import blocking_issue_count, collect_issues
from citiesai.snapshot import load_snapshot, snapshot_meta
from citiesai.suggestions import build_ask_suggestions

VENDOR_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "vendor/Cities2-DataExport/sample/latest.sample.json"
)


@pytest.fixture
def vendor_sample() -> dict:
    return load_snapshot(VENDOR_SAMPLE)


def test_collect_issues_corrupt_export() -> None:
    issues = collect_issues(
        {
            "ok": False,
            "mod_installed": True,
            "paths": {},
            "export": {"corrupt": True, "error": "Expecting value"},
            "knowledge": {"encyclopedia": {"available": True}},
            "llm": {"configured": True},
        },
        None,
    )
    assert any(i["id"] == "export_corrupt" for i in issues)


def test_collect_issues_stale_export_and_signal() -> None:
    status = {
        "ok": False,
        "issue_count": 1,
        "mod_installed": True,
        "paths": {
            "game_dir": {"ok": True},
            "locale_cok": {"ok": True},
            "export_path": {"ok": True},
        },
        "export": {"stale": True, "age_seconds": 5600},
        "knowledge": {"encyclopedia": {"available": True}},
        "llm": {"configured": True},
    }
    metrics = {
        "signals": [
            {"id": "mobility", "status": "partial", "note": "mobility metrics are partial"},
        ]
    }
    issues = collect_issues(status, metrics)
    ids = {issue["id"] for issue in issues}
    assert "export_stale" in ids
    assert "signal_mobility" in ids
    assert blocking_issue_count(issues) >= 1


def test_collect_issues_maps_signal_to_plain_language() -> None:
    issues = collect_issues(
        {
            "ok": True,
            "mod_installed": True,
            "paths": {},
            "export": {"stale": False},
            "knowledge": {"encyclopedia": {"available": True}},
            "llm": {"configured": True},
        },
        {"signals": [{"id": "transit", "status": "partial", "note": "raw note"}]},
    )
    transit = next(i for i in issues if i["id"] == "signal_transit")
    assert transit["title"] == "Transit coverage unclear"
    assert "ask_prompt" in transit


def test_build_ask_suggestions_deficit() -> None:
    issues = [
        {
            "id": "signal_budget",
            "ask_prompt": "What should I fix in my budget to stop running a deficit?",
        }
    ]
    metrics = {"income": 100, "expense": 250}
    suggestions = build_ask_suggestions(issues, metrics)
    assert any("budget" in s.lower() for s in suggestions)


def test_api_issues_with_sample(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    export = tmp_path / "latest.json"
    export.write_text(VENDOR_SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    from citiesai import config as config_mod

    cfg = config_mod.CitiesAIConfig(export_path=export)
    monkeypatch.setattr("citiesai.gui.api.load_config", lambda: cfg)
    monkeypatch.setattr("citiesai.gui.api._enriched_status", lambda: {
        "ok": True,
        "mod_installed": True,
        "paths": {
            "game_dir": {"ok": True},
            "locale_cok": {"ok": True},
            "export_path": {"ok": True},
        },
        "export": {"stale": False},
        "knowledge": {"encyclopedia": {"available": True}},
        "llm": {"configured": False},
    })

    result = api_issues()
    assert result["ok"] is True
    assert isinstance(result["issues"], list)
    assert result["count"] == len(result["issues"])


def test_api_suggestions_with_sample(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    export = tmp_path / "latest.json"
    export.write_text(VENDOR_SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    from citiesai import config as config_mod

    cfg = config_mod.CitiesAIConfig(export_path=export)
    monkeypatch.setattr("citiesai.gui.api.load_config", lambda: cfg)
    monkeypatch.setattr("citiesai.gui.api._enriched_status", lambda: {
        "ok": True,
        "mod_installed": True,
        "paths": {},
        "export": {"stale": False},
        "knowledge": {"encyclopedia": {"available": True}},
        "llm": {"configured": True},
    })

    result = api_suggestions()
    assert result["ok"] is True
    assert len(result["suggestions"]) <= 5
    assert result["llm_configured"] is True


def test_extract_headline_metrics_signals(vendor_sample: dict) -> None:
    meta = snapshot_meta(vendor_sample, path=VENDOR_SAMPLE)
    metrics = extract_headline_metrics(vendor_sample, meta)
    assert isinstance(metrics["signals"], list)
