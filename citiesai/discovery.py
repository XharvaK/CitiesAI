from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from cities2_mcp.game_encyclopedia import EncyclopediaConfig, find_locale_cok

LOCALE_RELATIVE = Path("Cities2_Data") / "Content" / "Game" / "Locale.cok"
USER_DATA_RELATIVE = Path("AppData/LocalLow/Colossal Order/Cities Skylines II")
EXPORT_RELATIVE = USER_DATA_RELATIVE / "ModsData/CS2DataExport/latest.json"


@dataclass(frozen=True)
class DiscoveredPaths:
    game_dir: Path | None
    locale_cok: Path | None
    export_path: Path
    source: str


def _user_profile() -> Path:
    if sys.platform == "win32":
        profile = os.environ.get("USERPROFILE", "").strip()
        if profile:
            return Path(profile)
    return Path.home()


def default_export_path() -> Path:
    return _user_profile() / EXPORT_RELATIVE


def _locale_from_game_dir(game_dir: Path) -> Path | None:
    candidate = game_dir / LOCALE_RELATIVE
    return candidate if candidate.is_file() else None


def discover_game_pass_installs() -> list[Path]:
    if sys.platform != "win32":
        return []
    xbox_root = Path("C:/XboxGames")
    if not xbox_root.is_dir():
        return []
    found: list[Path] = []
    for content_dir in xbox_root.glob("*/Content"):
        if _locale_from_game_dir(content_dir):
            found.append(content_dir.resolve())
    return found


def discover_steam_game_dir() -> Path | None:
    discovery = find_locale_cok(EncyclopediaConfig())
    if discovery.available and discovery.game_dir:
        return discovery.game_dir.resolve()
    return None


def discover_paths() -> DiscoveredPaths:
    export_path = default_export_path()

    env_game = os.environ.get("CITIES2_GAME_DIR", "").strip()
    if env_game:
        game_dir = Path(env_game).expanduser()
        locale = _locale_from_game_dir(game_dir)
        if locale:
            return DiscoveredPaths(game_dir=game_dir.resolve(), locale_cok=locale, export_path=export_path, source="env")

    env_locale = os.environ.get("CITIES2_LOCALE_COK", "").strip()
    if env_locale:
        locale_path = Path(env_locale).expanduser()
        if locale_path.is_file():
            game_dir = locale_path.parents[3] if len(locale_path.parents) > 3 else None
            return DiscoveredPaths(
                game_dir=game_dir.resolve() if game_dir else None,
                locale_cok=locale_path.resolve(),
                export_path=export_path,
                source="env_locale",
            )

    for game_dir in discover_game_pass_installs():
        locale = _locale_from_game_dir(game_dir)
        if locale:
            return DiscoveredPaths(
                game_dir=game_dir,
                locale_cok=locale,
                export_path=export_path,
                source="game_pass",
            )

    steam_dir = discover_steam_game_dir()
    if steam_dir:
        locale = _locale_from_game_dir(steam_dir)
        if locale:
            return DiscoveredPaths(
                game_dir=steam_dir,
                locale_cok=locale,
                export_path=export_path,
                source="steam",
            )

    return DiscoveredPaths(game_dir=None, locale_cok=None, export_path=export_path, source="none")
