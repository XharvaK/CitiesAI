from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .snapshot import SnapshotMeta, pick, pick_group

_CONTINUE_GAME_RELATIVE = (
    Path("AppData/LocalLow/Colossal Order/Cities Skylines II") / "continue_game.json"
)


def _user_profile() -> Path:
    if sys.platform == "win32":
        profile = os.environ.get("USERPROFILE", "").strip()
        if profile:
            return Path(profile)
    return Path.home()


def continue_game_title() -> str | None:
    path = _user_profile() / _CONTINUE_GAME_RELATIVE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    title = data.get("title") if isinstance(data, dict) else None
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def city_name_from_snapshot(snapshot: dict[str, Any]) -> str | None:
    city = pick_group(snapshot, "City")
    name = pick(city, "CityName", "city_name")
    if name is None:
        return None
    text = str(name).strip()
    return text or None


def resolve_city_display_name(
    snapshot: dict[str, Any],
    meta: SnapshotMeta | None = None,
) -> str:
    if meta and meta.city_name:
        return meta.city_name
    from_export = city_name_from_snapshot(snapshot)
    if from_export:
        return from_export
    from_continue = continue_game_title()
    if from_continue:
        return from_continue
    return "Your city"
