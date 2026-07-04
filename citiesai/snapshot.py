from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .constants import STALE_AFTER_SECONDS

JsonDict = dict[str, Any]


def pick(obj: Any, *names: str, default: Any = None) -> Any:
    if not isinstance(obj, dict):
        return default
    index = {str(key).lower().replace("_", ""): key for key in obj}
    for name in names:
        normalized = name.lower().replace("_", "")
        key = index.get(normalized)
        if key is not None:
            return obj[key]
    return default


def pick_group(snapshot: JsonDict, group: str) -> JsonDict:
    value = pick(snapshot, group)
    return value if isinstance(value, dict) else {}


def load_snapshot(path: Path) -> JsonDict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_snapshot_safe(path: Path) -> tuple[JsonDict | None, str | None]:
    try:
        return load_snapshot(path), None
    except (json.JSONDecodeError, OSError, UnicodeError) as exc:
        return None, str(exc)


@dataclass(frozen=True)
class SnapshotMeta:
    path: Path
    schema_version: str | None
    exported_at_utc: str | None
    city_name: str | None
    age_seconds: float | None
    stale: bool


def snapshot_meta(snapshot: JsonDict, *, path: Path, stale_after_seconds: float = STALE_AFTER_SECONDS) -> SnapshotMeta:
    exported_raw = pick(snapshot, "ExportedAtUtc", "exported_at_utc")
    age_seconds: float | None = None
    stale = False
    if isinstance(exported_raw, str) and exported_raw:
        try:
            normalized = exported_raw.replace("Z", "+00:00")
            exported_at = datetime.fromisoformat(normalized)
            if exported_at.tzinfo is None:
                exported_at = exported_at.replace(tzinfo=UTC)
            age_seconds = max(0.0, (datetime.now(UTC) - exported_at).total_seconds())
            stale = age_seconds > stale_after_seconds
        except ValueError:
            pass

    city = pick_group(snapshot, "City")
    city_name = pick(city, "CityName", "city_name")
    if city_name is not None:
        city_name = str(city_name)

    return SnapshotMeta(
        path=path,
        schema_version=pick(snapshot, "SchemaVersion", "schema_version"),
        exported_at_utc=exported_raw if isinstance(exported_raw, str) else None,
        city_name=city_name,
        age_seconds=age_seconds,
        stale=stale,
    )
