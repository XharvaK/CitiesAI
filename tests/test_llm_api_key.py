from __future__ import annotations

from pathlib import Path

import pytest

from citiesai.config import CitiesAIConfig
from citiesai.env_store import read_env_var


def test_api_test_key_honors_provider_override(
    isolated_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from citiesai.gui.api import api_test_key

    cfg = CitiesAIConfig()
    captured: dict[str, str] = {}

    def fake_test_api_key(*, cfg: CitiesAIConfig) -> dict[str, str | bool]:
        captured["provider"] = cfg.llm_provider
        captured["base_url"] = cfg.llm_base_url
        captured["model"] = cfg.llm_model
        return {"ok": True, "model": cfg.llm_model}

    monkeypatch.setattr("citiesai.gui.api.load_config", lambda: cfg)
    monkeypatch.setattr("citiesai.gui.api.test_api_key", fake_test_api_key)

    result = api_test_key({"llm_provider": "openai", "llm_model": "gpt-5.5"})
    assert result["ok"] is True
    assert captured["provider"] == "openai"
    assert captured["base_url"] == "https://api.openai.com/v1"
    assert captured["model"] == "gpt-5.5"


def test_api_save_key_derives_env_from_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from citiesai.gui.api import api_save_key

    monkeypatch.setattr("citiesai.env_store._config_dir", lambda: tmp_path)

    result = api_save_key({"api_key": "sk-openai-test", "llm_provider": "openai"})
    assert result["ok"] is True
    assert result["env_name"] == "OPENAI_API_KEY"
    assert read_env_var("OPENAI_API_KEY") == "sk-openai-test"
