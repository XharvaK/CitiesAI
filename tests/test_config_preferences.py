"""Config migration and preference persistence for civic-command redesign."""

from __future__ import annotations

from pathlib import Path

from citiesai.config import (
    DEFAULT_ADVISOR_STYLE,
    load_config,
    normalize_advisor_style,
    set_advisor_style,
    set_watch_enabled,
)


def test_normalize_advisor_style_defaults() -> None:
    assert normalize_advisor_style(None) == DEFAULT_ADVISOR_STYLE
    assert normalize_advisor_style("nope") == DEFAULT_ADVISOR_STYLE
    assert normalize_advisor_style("Civic") == "civic"
    assert normalize_advisor_style("analyst") == "analyst"


def test_legacy_config_gets_advisor_and_watch_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[paths]\nexport_path = "C:/tmp/latest.json"\n\n[ui]\ncomayor_enabled = true\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("citiesai.config.config_path", lambda: cfg_path)
    cfg = load_config()
    assert cfg.advisor_style == "civic"
    assert cfg.watch_enabled is False
    assert cfg.comayor_enabled is True


def test_advisor_style_and_watch_persist(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text("", encoding="utf-8")
    monkeypatch.setattr("citiesai.config.config_path", lambda: cfg_path)

    set_advisor_style("analyst")
    set_watch_enabled(enabled=True)
    cfg = load_config()
    assert cfg.advisor_style == "analyst"
    assert cfg.watch_enabled is True

    text = cfg_path.read_text(encoding="utf-8")
    assert 'advisor_style = "analyst"' in text
    assert "watch_enabled = true" in text
