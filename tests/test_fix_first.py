from __future__ import annotations

from citiesai.fix_first import build_fix_first_playbook, urgency_weight


def test_urgency_weight_utilities_above_leaving() -> None:
    assert urgency_weight({"id": "city_sewage_pressure", "severity": "warn"}) < urgency_weight(
        {"id": "city_citizens_leaving", "severity": "warn"}
    )


def test_fix_first_ranks_sewage_above_citizens_leaving() -> None:
    playbook = build_fix_first_playbook(
        issues=[
            {
                "id": "city_citizens_leaving",
                "kind": "city",
                "severity": "warn",
                "title": "Citizens are moving away",
                "detail": "Many households leaving",
                "ask_prompt": "Why are citizens leaving?",
            },
            {
                "id": "city_sewage_pressure",
                "kind": "city",
                "severity": "warn",
                "title": "Sewage and treatment under pressure",
                "detail": "No sewage treatment capacity",
                "ask_prompt": "How do I fix sewage?",
            },
            {
                "id": "city_wellbeing_low",
                "kind": "city",
                "severity": "warn",
                "title": "City wellbeing is low",
                "detail": "Wellbeing 40",
                "ask_prompt": "Why is wellbeing low?",
            },
        ]
    )
    assert playbook[0]["id"] == "city_sewage_pressure"
    assert playbook[0]["title"].startswith("Sewage")


def test_fix_first_error_utility_beats_warn_leaving() -> None:
    playbook = build_fix_first_playbook(
        issues=[
            {
                "id": "city_citizens_leaving",
                "kind": "city",
                "severity": "warn",
                "title": "Citizens are moving away",
                "detail": "Leaving",
                "ask_prompt": "Why?",
            },
            {
                "id": "city_sewage_pressure",
                "kind": "city",
                "severity": "error",
                "title": "Sewage and treatment under pressure",
                "detail": "Capacity 0",
                "ask_prompt": "Fix sewage",
            },
        ]
    )
    assert playbook[0]["id"] == "city_sewage_pressure"
