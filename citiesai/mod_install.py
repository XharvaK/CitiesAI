from __future__ import annotations

import os
import shutil
import sys
from importlib import resources
from pathlib import Path

USER_DATA_RELATIVE = Path("AppData/LocalLow/Colossal Order/Cities Skylines II")
MOD_RELATIVE = USER_DATA_RELATIVE / "Mods/CS2DataExport"


def default_mod_install_path() -> Path:
    profile = os.environ.get("USERPROFILE", "").strip() or str(Path.home())
    return Path(profile) / MOD_RELATIVE


def bundled_mod_source() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "citiesai" / "bundled" / "CS2DataExport")
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "bundled" / "CS2DataExport")
    try:
        pkg = resources.files("citiesai.bundled").joinpath("CS2DataExport")
        if pkg.is_dir():
            candidates.append(Path(str(pkg)))
    except (ModuleNotFoundError, TypeError, FileNotFoundError):
        pass
    repo_root = Path(__file__).resolve().parents[1]
    candidates.extend(
        [
            repo_root / "packaging" / "bundled" / "CS2DataExport",
            repo_root / "vendor" / "Cities2-DataExport" / "bin" / "Release" / "net48",
        ]
    )
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.dll")):
            return candidate
    return None


def mod_installed() -> bool:
    target = default_mod_install_path()
    return target.is_dir() and any(target.glob("*.dll"))


def install_mod(*, target: Path | None = None) -> dict[str, str | bool]:
    source = bundled_mod_source()
    if source is None:
        return {
            "ok": False,
            "error": "Bundled CS2 Data Export mod not found. Reinstall CitiesAI or build from source.",
        }
    dest = target or default_mod_install_path()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
    except PermissionError:
        return {
            "ok": False,
            "error": (
                "Could not copy mod files. Is Cities: Skylines II running? "
                "Close the game and try again."
            ),
        }
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "source": str(source), "installed_to": str(dest)}
