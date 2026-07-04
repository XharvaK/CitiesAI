"""CitiesAI release version (canonical: pyproject.toml [project].version)."""

from __future__ import annotations

import tomllib
from pathlib import Path

_FALLBACK_VERSION = "0.1.0"


def _load_version() -> str:
    pyproject = Path(__file__).resolve().parents[1].parent / "pyproject.toml"
    if not pyproject.is_file():
        return _FALLBACK_VERSION
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return _FALLBACK_VERSION
    version = data.get("project", {}).get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return _FALLBACK_VERSION


__version__ = _load_version()
