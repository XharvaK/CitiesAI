from __future__ import annotations

from citiesai.ask_core import classify_ask_intent, needs_knowledge_retrieval
from citiesai.llm import (
    LLMSettings,
    _chat_payload,
    _supports_temperature,
    build_system_prompt,
)
from citiesai.version import __version__


def test_classify_ask_intent_routes() -> None:
    assert classify_ask_intent("How do I update CitiesAI?") == "app"
    assert classify_ask_intent("Where do I put my API key?") == "app"
    assert classify_ask_intent("My data export is missing") == "setup"
    assert classify_ask_intent("Is this a pop farm or a megapolis?") == "classification"
    assert classify_ask_intent("Why is my budget negative?") == "gameplay"
    assert needs_knowledge_retrieval("classification") is False
    assert needs_knowledge_retrieval("gameplay") is True


def test_build_system_prompt_practical_no_sources() -> None:
    prompt = build_system_prompt()
    assert "No Sources section" in prompt
    assert "concrete in-game actions" in prompt
    assert "do not number the diagnosis" in prompt
    assert "End with a short Sources line" not in prompt
    assert "staleness" in prompt
    assert "stale or partial" not in prompt


def test_build_system_prompt_hardened() -> None:
    prompt = build_system_prompt()
    assert f"CitiesAI v{__version__}" in prompt
    assert "Settings → Updates" in prompt
    assert "github.com/XharvaK/CitiesAI/releases" in prompt
    assert "Paradox Mods unless they explicitly" in prompt
    assert "close CS2" in prompt
    assert "install/reinstall export mod" in prompt
    assert "skip the numbered action list" in prompt
    assert "City character / classification / judgment" in prompt
    assert "pop farm or megapolis" in prompt
    assert "Answer the question asked" in prompt
    assert "unsolicited optimization lists" in prompt
    assert "only when routing says to use it" in prompt
    assert "Never invent metrics" in prompt
    assert "patch versions" in prompt
    assert "Game Encyclopedia" in prompt
    assert "in-game city currency" in prompt
    assert "0-100 indices" in prompt
    assert "commuters/tourists" in prompt
    assert "Cities: Skylines II only" in prompt
    assert "No cheats, save editing" in prompt

    agentic = build_system_prompt(agentic=True)
    assert f"CitiesAI v{__version__}" in agentic
    assert "fetch metric groups" in agentic
    assert "at most 8 tool rounds" in agentic

    agentic_custom = build_system_prompt(agentic=True, tool_rounds=3)
    assert "at most 3 tool rounds" in agentic_custom
    assert "at most 2 tool rounds" not in agentic_custom
    assert "at most 2 tool rounds" not in agentic


def test_build_system_prompt_advisor_styles_change_tone_only() -> None:
    civic = build_system_prompt(advisor_style="civic")
    conversational = build_system_prompt(advisor_style="conversational")
    analyst = build_system_prompt(advisor_style="analyst")
    assert "Advisor style: Civic" in civic
    assert "Advisor style: Conversational" in conversational
    assert "Advisor style: Analyst" in analyst
    # Shared factual invariants remain across styles.
    for prompt in (civic, conversational, analyst):
        assert "Never invent metrics" in prompt
        assert "No Sources section" in prompt
        assert "concrete in-game actions" in prompt
        assert "when using gameplay output format" in prompt.lower()
        assert "Answer the question asked" in prompt
    assert "Warm, game-native" in conversational
    assert "Technical and detailed" in analyst
    assert civic != conversational != analyst

def test_chat_payload_omits_temperature_for_gpt5() -> None:
    settings = LLMSettings(
        base_url="https://api.openai.com/v1",
        model="gpt-5.5",
        api_key="sk-test",
        api_key_env="OPENAI_API_KEY",
    )
    payload = _chat_payload([{"role": "user", "content": "hi"}], settings, stream=False)
    assert "temperature" not in payload


def test_chat_payload_includes_temperature_for_mistral() -> None:
    settings = LLMSettings(
        base_url="https://api.mistral.ai/v1",
        model="mistral-medium-latest",
        api_key="sk-test",
        api_key_env="MISTRAL_API_KEY",
    )
    payload = _chat_payload([{"role": "user", "content": "hi"}], settings, stream=False)
    assert payload["temperature"] == 0.3


def test_chat_payload_includes_temperature_for_gpt4o() -> None:
    settings = LLMSettings(
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        api_key="sk-test",
        api_key_env="OPENAI_API_KEY",
    )
    assert _supports_temperature(settings) is True
    payload = _chat_payload([{"role": "user", "content": "hi"}], settings, stream=False)
    assert payload["temperature"] == 0.3
