"""CitiesAI release version (canonical: pyproject.toml [project].version)."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

_FALLBACK_VERSION = "0.6.1"


def _pyproject_path() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [here.parents[1] / "pyproject.toml"]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.insert(0, Path(meipass) / "pyproject.toml")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _load_version() -> str:
    pyproject = _pyproject_path()
    if pyproject is None:
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
