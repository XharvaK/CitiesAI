from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .discovery import DiscoveredPaths, default_export_path, discover_paths
from .env_store import load_env_file

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


LEGACY_LLM_MODEL = "mistral-small-latest"
DEFAULT_LLM_MODEL = "mistral-medium-latest"
DEFAULT_MAX_TOOL_ROUNDS = 8
DEFAULT_ADVISOR_STYLE = "civic"
ADVISOR_STYLES = frozenset({"civic", "conversational", "analyst"})


def normalize_advisor_style(value: Any) -> str:
    style = str(value or "").strip().lower()
    if style in ADVISOR_STYLES:
        return style
    return DEFAULT_ADVISOR_STYLE


@dataclass
class CitiesAIConfig:
    game_dir: Path | None = None
    locale_cok: Path | None = None
    export_path: Path | None = None
    llm_provider: str = "mistral"
    llm_model: str = DEFAULT_LLM_MODEL
    llm_base_url: str = "https://api.mistral.ai/v1"
    llm_api_key_env: str = "MISTRAL_API_KEY"
    llm_max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS
    llm_agentic_enabled: bool = True
    onboarding_complete: bool = False
    comayor_enabled: bool = True
    advisor_style: str = DEFAULT_ADVISOR_STYLE
    watch_enabled: bool = False
    check_updates_on_startup: bool = True
    update_last_check_utc: str | None = None
    update_dismissed_version: str | None = None

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
                "max_tool_rounds": self.llm_max_tool_rounds,
                "agentic": self.llm_agentic_enabled,
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
        lines.append(f"max_tool_rounds = {self.llm_max_tool_rounds}")
        lines.append(f"agentic = {'true' if self.llm_agentic_enabled else 'false'}")
        lines.append("")
        lines.append("[app]")
        lines.append(f"onboarding_complete = {'true' if self.onboarding_complete else 'false'}")
        lines.append("")
        lines.append("[ui]")
        lines.append(f"comayor_enabled = {'true' if self.comayor_enabled else 'false'}")
        lines.append(f'advisor_style = "{normalize_advisor_style(self.advisor_style)}"')
        lines.append(f"watch_enabled = {'true' if self.watch_enabled else 'false'}")
        lines.append("")
        lines.append("[updates]")
        lines.append(f"check_on_startup = {'true' if self.check_updates_on_startup else 'false'}")
        if self.update_last_check_utc:
            lines.append(f'last_check_utc = "{_escape_toml(self.update_last_check_utc)}"')
        if self.update_dismissed_version:
            lines.append(f'dismissed_version = "{_escape_toml(self.update_dismissed_version)}"')
        lines.append("")
        content = "\n".join(lines) + "\n"
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        try:
            from .cache import invalidate_config_cache

            invalidate_config_cache()
        except ImportError:
            pass
        return path


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def load_config() -> CitiesAIConfig:
    load_env_file()
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
    app = data.get("app", {})
    updates = data.get("updates", {})

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
    if llm.get("max_tool_rounds") is not None:
        try:
            cfg.llm_max_tool_rounds = max(1, int(llm["max_tool_rounds"]))
        except (TypeError, ValueError):
            pass
    if "agentic" in llm:
        cfg.llm_agentic_enabled = bool(llm["agentic"])

    if cfg.llm_model == LEGACY_LLM_MODEL:
        cfg.llm_model = DEFAULT_LLM_MODEL
        cfg.write()

    if "onboarding_complete" in app:
        cfg.onboarding_complete = bool(app["onboarding_complete"])

    ui = data.get("ui", {})
    if "comayor_enabled" in ui:
        cfg.comayor_enabled = bool(ui["comayor_enabled"])
    if "advisor_style" in ui:
        cfg.advisor_style = normalize_advisor_style(ui.get("advisor_style"))
    if "watch_enabled" in ui:
        cfg.watch_enabled = bool(ui["watch_enabled"])

    if "check_on_startup" in updates:
        cfg.check_updates_on_startup = bool(updates["check_on_startup"])
    if updates.get("last_check_utc"):
        cfg.update_last_check_utc = str(updates["last_check_utc"])
    if updates.get("dismissed_version"):
        cfg.update_dismissed_version = str(updates["dismissed_version"])

    return cfg


def set_onboarding_complete(*, complete: bool = True) -> Path:
    cfg = load_config()
    cfg.onboarding_complete = complete
    return cfg.write()


def set_comayor_enabled(*, enabled: bool) -> Path:
    cfg = load_config()
    cfg.comayor_enabled = bool(enabled)
    return cfg.write()


def set_advisor_style(style: str) -> Path:
    cfg = load_config()
    cfg.advisor_style = normalize_advisor_style(style)
    return cfg.write()


def set_watch_enabled(*, enabled: bool) -> Path:
    cfg = load_config()
    cfg.watch_enabled = bool(enabled)
    return cfg.write()


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
