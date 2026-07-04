from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _config_dir() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "CitiesAI"
    return Path.home() / ".config" / "citiesai"


def env_file_path() -> Path:
    return _config_dir() / ".env"


def load_env_file() -> None:
    path = env_file_path()
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if not match:
            continue
        key, raw_value = match.group(1), match.group(2)
        if key in os.environ:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


def save_env_var(name: str, value: str) -> Path:
    path = env_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    found = False
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                lines.append(f'{name}="{_escape(value)}"')
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f'{name}="{_escape(value)}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[name] = value
    return path


def clear_env_var(name: str) -> None:
    path = env_file_path()
    if not path.is_file():
        os.environ.pop(name, None)
        return
    kept = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.strip().startswith(f"{name}=")]
    if kept:
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    os.environ.pop(name, None)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
