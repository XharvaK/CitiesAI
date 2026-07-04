from __future__ import annotations

from citiesai.llm import build_system_prompt


def test_build_system_prompt_practical_no_sources() -> None:
    prompt = build_system_prompt()
    assert "No Sources section" in prompt
    assert "concrete in-game actions" in prompt
    assert "do not number the diagnosis" in prompt
    assert "End with a short Sources line" not in prompt
    assert "staleness" in prompt
    assert "stale or partial" not in prompt
