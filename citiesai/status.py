from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import CitiesAIConfig, config_path, load_config
from .discovery import discover_paths
from .knowledge import knowledge_status, reset_knowledge_cache
from .llm import resolve_llm_settings
from .snapshot import load_snapshot_safe, snapshot_meta


def _path_entry(label: str, path: Path | None, *, must_exist: bool) -> dict[str, Any]:
    entry: dict[str, Any] = {"label": label, "path": str(path) if path else None, "ok": True}
    if path is None:
        entry["ok"] = False
        entry["error"] = "missing"
        return entry
    if must_exist and not path.exists():
        entry["ok"] = False
        entry["error"] = "path does not exist"
    return entry


def collect_status_report(cfg: CitiesAIConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    discovered = discover_paths()
    issues = 0

    game_dir = cfg.resolved_game_dir()
    locale_cok = cfg.resolved_locale_cok()
    export_path = cfg.resolved_export_path()

    paths = {
        "game_dir": _path_entry("game_dir", game_dir, must_exist=True),
        "locale_cok": _path_entry("locale_cok", locale_cok, must_exist=True),
        "export_path": _path_entry("export_path", export_path, must_exist=True),
    }
    for entry in paths.values():
        if not entry["ok"]:
            issues += 1

    export_block: dict[str, Any] | None = None
    if export_path.is_file():
        snapshot, export_err = load_snapshot_safe(export_path)
        if snapshot is None:
            export_block = {"corrupt": True, "error": export_err}
            issues += 1
        else:
            meta = snapshot_meta(snapshot, path=export_path)
            export_block = {
                "schema_version": meta.schema_version,
                "city_name": meta.city_name,
                "exported_at_utc": meta.exported_at_utc,
                "age_seconds": meta.age_seconds,
                "stale": meta.stale,
            }
            if meta.stale:
                issues += 1

    knowledge_block: dict[str, Any]
    try:
        reset_knowledge_cache()
        knowledge_block = knowledge_status()
        enc = knowledge_block.get("encyclopedia", {})
        if not enc.get("available"):
            issues += 1
    except Exception as exc:  # noqa: BLE001 - surface in status payload
        knowledge_block = {"error": str(exc)}
        issues += 1

    llm = resolve_llm_settings(cfg)
    llm_block: dict[str, Any] = {
        "configured": llm is not None,
        "provider": cfg.llm_provider,
        "model": cfg.llm_model,
        "api_key_env": cfg.llm_api_key_env,
    }
    if llm:
        llm_block["api_key_set"] = True
    else:
        llm_block["api_key_set"] = False
        llm_block["hint"] = "Set MISTRAL_API_KEY for LLM answers in the GUI."

    cfg_file = config_path()
    return {
        "ok": issues == 0,
        "issue_count": issues,
        "config_path": str(cfg_file) if cfg_file.is_file() else None,
        "discovery_source": discovered.source,
        "paths": paths,
        "export": export_block,
        "knowledge": knowledge_block,
        "llm": llm_block,
    }
