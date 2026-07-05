"""Process-local caches for config and export snapshots."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from .config import CitiesAIConfig
from .config import load_config as _load_config_uncached
from .snapshot import load_snapshot_safe

_lock = threading.Lock()
_config_cache: tuple[float, CitiesAIConfig] | None = None
_export_cache: dict[str, tuple[float, dict[str, Any] | None, str | None]] = {}


def load_config_cached() -> CitiesAIConfig:
    global _config_cache
    from .config import config_path

    cfg_path = config_path()
    mtime = cfg_path.stat().st_mtime if cfg_path.is_file() else 0.0
    with _lock:
        if _config_cache and _config_cache[0] == mtime:
            return _config_cache[1]
    cfg = _load_config_uncached()
    with _lock:
        _config_cache = (mtime, cfg)
    return cfg


def invalidate_config_cache() -> None:
    global _config_cache
    with _lock:
        _config_cache = None


def load_export_cached(export_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = export_path.expanduser()
    path_key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime if path.is_file() else 0.0
    except OSError:
        mtime = 0.0
    with _lock:
        cached = _export_cache.get(path_key)
        if cached and cached[0] == mtime:
            return cached[1], cached[2]
    snapshot, err = load_snapshot_safe(path)
    with _lock:
        _export_cache[path_key] = (mtime, snapshot, err)
    return snapshot, err
