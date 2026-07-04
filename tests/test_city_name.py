from __future__ import annotations

import json
from pathlib import Path

import pytest

from citiesai.city_name import continue_game_title, resolve_city_display_name
from citiesai.snapshot import snapshot_meta


def test_resolve_city_display_name_prefers_export(tmp_path: Path) -> None:
    snapshot = {"City": {"city_name": "Evergreen Bay"}}
    meta = snapshot_meta(snapshot, path=tmp_path / "latest.json")
    assert resolve_city_display_name(snapshot, meta) == "Evergreen Bay"


def test_resolve_city_display_name_uses_continue_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    continue_path = tmp_path / "continue_game.json"
    continue_path.write_text(json.dumps({"title": "Fabius"}), encoding="utf-8")
    monkeypatch.setattr("citiesai.city_name._CONTINUE_GAME_RELATIVE", Path("continue_game.json"))
    monkeypatch.setattr(
        "citiesai.city_name._user_profile",
        lambda: tmp_path,
    )

    snapshot = {"City": {"CityName": None}}
    meta = snapshot_meta(snapshot, path=tmp_path / "latest.json")
    assert meta.city_name is None
    assert resolve_city_display_name(snapshot, meta) == "Fabius"
    assert continue_game_title() == "Fabius"


def test_resolve_city_display_name_defaults_to_your_city(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "citiesai.city_name._CONTINUE_GAME_RELATIVE",
        tmp_path / "missing" / "continue_game.json",
    )
    snapshot = {"City": {}}
    meta = snapshot_meta(snapshot, path=tmp_path / "latest.json")
    assert resolve_city_display_name(snapshot, meta) == "Your city"
