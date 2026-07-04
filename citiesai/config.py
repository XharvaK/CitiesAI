from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .discovery import DiscoveredPaths, default_export_path, discover_paths

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py3.11+
    import tomli as tomllib  # type: ignore[no-redef]


def config_dir() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "CitiesAI"
    return Path.home() / ".config" / "citiesai"


def config_path() -> Path:
    return config_dir() / "config.toml"


@dataclass
class CitiesAIConfig:
    game_dir: Path | None = None
    locale_cok: Path | None = None
    export_path: Path | None = None
    llm_provider: str = "mistral"
    llm_model: str = "mistral-small-latest"
    llm_base_url: str = "https://api.mistral.ai/v1"
    llm_api_key_env: str = "MISTRAL_API_KEY"

    def resolved_export_path(self) -> Path:
        if self.export_path:
            return self.export_path.expanduser()
        env = os.environ.get("CITIESAI_EXPORT_PATH", "").strip()
        if env:
            return Path(env).expanduser()
        return default_export_path()

    def resolved_game_dir(self) -> Path | None:
        env = os.environ.get("CITIES2_GAME_DIR", "").strip()
        if env:
            return Path(env).expanduser()
        return self.game_dir.expanduser() if self.game_dir else None

    def resolved_locale_cok(self) -> Path | None:
        env = os.environ.get("CITIES2_LOCALE_COK", "").strip()
        if env:
            return Path(env).expanduser()
        if self.locale_cok:
            return self.locale_cok.expanduser()
        game_dir = self.resolved_game_dir()
        if game_dir:
            candidate = game_dir / "Cities2_Data/Content/Game/Locale.cok"
            if candidate.is_file():
                return candidate
        return None

    def llm_api_key(self) -> str | None:
        key = os.environ.get(self.llm_api_key_env, "").strip()
        return key or None

    def to_toml_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "paths": {},
            "llm": {
                "provider": self.llm_provider,
                "model": self.llm_model,
                "base_url": self.llm_base_url,
                "api_key_env": self.llm_api_key_env,
            },
        }
        if self.game_dir:
            payload["paths"]["game_dir"] = str(self.game_dir)
        if self.locale_cok:
            payload["paths"]["locale_cok"] = str(self.locale_cok)
        if self.export_path:
            payload["paths"]["export_path"] = str(self.export_path)
        return payload

    def write(self) -> Path:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# CitiesAI configuration", ""]
        lines.append("[paths]")
        if self.game_dir:
            lines.append(f'game_dir = "{_escape_toml(str(self.game_dir))}"')
        if self.locale_cok:
            lines.append(f'locale_cok = "{_escape_toml(str(self.locale_cok))}"')
        if self.export_path:
            lines.append(f'export_path = "{_escape_toml(str(self.export_path))}"')
        lines.append("")
        lines.append("[llm]")
        lines.append(f'provider = "{self.llm_provider}"')
        lines.append(f'model = "{self.llm_model}"')
        lines.append(f'base_url = "{self.llm_base_url}"')
        lines.append(f'api_key_env = "{self.llm_api_key_env}"')
        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return path


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\")


def load_config() -> CitiesAIConfig:
    discovered = discover_paths()
    cfg = CitiesAIConfig(
        game_dir=discovered.game_dir,
        locale_cok=discovered.locale_cok,
        export_path=discovered.export_path,
    )

    path = config_path()
    if not path.is_file():
        return cfg

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    paths = data.get("paths", {})
    llm = data.get("llm", {})

    if paths.get("game_dir"):
        cfg.game_dir = Path(str(paths["game_dir"]))
    if paths.get("locale_cok"):
        cfg.locale_cok = Path(str(paths["locale_cok"]))
    if paths.get("export_path"):
        cfg.export_path = Path(str(paths["export_path"]))

    if llm.get("provider"):
        cfg.llm_provider = str(llm["provider"])
    if llm.get("model"):
        cfg.llm_model = str(llm["model"])
    if llm.get("base_url"):
        cfg.llm_base_url = str(llm["base_url"])
    if llm.get("api_key_env"):
        cfg.llm_api_key_env = str(llm["api_key_env"])

    return cfg


def apply_config_to_env(cfg: CitiesAIConfig) -> None:
    game_dir = cfg.resolved_game_dir()
    locale_cok = cfg.resolved_locale_cok()
    export_path = cfg.resolved_export_path()

    if game_dir and not os.environ.get("CITIES2_GAME_DIR"):
        os.environ["CITIES2_GAME_DIR"] = str(game_dir)
    if locale_cok and not os.environ.get("CITIES2_LOCALE_COK"):
        os.environ["CITIES2_LOCALE_COK"] = str(locale_cok)
    if export_path and not os.environ.get("CITIESAI_EXPORT_PATH"):
        os.environ["CITIESAI_EXPORT_PATH"] = str(export_path)


def merge_discovered(cfg: CitiesAIConfig, discovered: DiscoveredPaths) -> CitiesAIConfig:
    if cfg.game_dir is None and discovered.game_dir:
        cfg.game_dir = discovered.game_dir
    if cfg.locale_cok is None and discovered.locale_cok:
        cfg.locale_cok = discovered.locale_cok
    if cfg.export_path is None:
        cfg.export_path = discovered.export_path
    return cfg
