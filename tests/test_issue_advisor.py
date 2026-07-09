"""Tests for deterministic issue-advisor enrichment."""

from __future__ import annotations

from citiesai.issue_advisor import enrich_issue_advisor, enrich_issues, rank_issues_for_queue


def test_enrich_issue_advisor_known_id() -> None:
    issue = {
        "id": "city_sewage_pressure",
        "kind": "city",
        "title": "Sewage under pressure",
        "detail": "Fulfillment 12%",
        "hint": "Add treatment",
        "severity": "error",
        "session_count": 3,
        "ask_prompt": "How do I fix sewage?",
    }
    enriched = enrich_issue_advisor(issue)
    assert enriched["domain"] == "services"
    assert enriched["evidence"]
    assert any(row["label"] == "Measured" for row in enriched["evidence"])
    assert any("Persistence" in row["label"] for row in enriched["evidence"])
    assert enriched["likely_causes"]
    assert enriched["actions"]
    assert enriched["ask_prompt"] == "How do I fix sewage?"
    # Original fields preserved; no invented metrics beyond provided detail.
    assert enriched["detail"] == "Fulfillment 12%"
    assert "12%" in enriched["evidence"][0]["value"]


def test_enrich_issue_advisor_does_not_invent_causes_without_detail() -> None:
    issue = {
        "id": "unknown_custom_issue",
        "kind": "city",
        "title": "Mystery pressure",
        "severity": "warn",
    }
    enriched = enrich_issue_advisor(issue)
    assert enriched["domain"] == "city"
    assert enriched["likely_causes"] == []
    assert enriched["actions"]
    assert "Mystery pressure" in enriched["ask_prompt"]


def test_rank_issues_for_queue_prefers_city_errors() -> None:
    issues = enrich_issues(
        [
            {
                "id": "setup_mod",
                "kind": "setup",
                "severity": "error",
                "title": "Mod missing",
            },
            {
                "id": "city_demand_weak",
                "kind": "city",
                "severity": "info",
                "title": "Weak demand",
            },
            {
                "id": "city_sewage_pressure",
                "kind": "city",
                "severity": "error",
                "title": "Sewage",
            },
        ]
    )
    ranked = rank_issues_for_queue(issues)
    assert ranked[0]["id"] == "city_sewage_pressure"
    assert ranked[-1]["id"] == "setup_mod"
