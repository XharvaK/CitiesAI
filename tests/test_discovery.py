from __future__ import annotations

from citiesai.discovery import discover_game_pass_installs, discover_paths


def test_discover_paths_returns_export_path() -> None:
    discovered = discover_paths()
    assert discovered.export_path.name == "latest.json"
    assert "CS2DataExport" in str(discovered.export_path)


def test_game_pass_discovery_is_list() -> None:
    installs = discover_game_pass_installs()
    assert isinstance(installs, list)
    for path in installs:
        assert path.is_dir()
        locale = path / "Cities2_Data/Content/Game/Locale.cok"
        assert locale.is_file()
