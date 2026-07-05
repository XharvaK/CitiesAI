"""Shared pytest fixtures — isolate config from the real user profile."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect CitiesAI config to a temp directory (Windows via APPDATA)."""
    root = tmp_path / "AppData" / "Roaming"
    cfg_dir = root / "CitiesAI"
    cfg_dir.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(root))
    monkeypatch.setenv("CITIESAI_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setattr("citiesai.config.config_dir", lambda: cfg_dir)
    monkeypatch.setattr("citiesai.env_store._config_dir", lambda: cfg_dir)
    return cfg_dir
