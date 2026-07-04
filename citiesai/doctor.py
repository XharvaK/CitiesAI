from __future__ import annotations

from pathlib import Path

from .config import CitiesAIConfig, config_path, load_config
from .discovery import discover_paths
from .knowledge import knowledge_status, reset_knowledge_cache
from .llm import resolve_llm_settings
from .snapshot import load_snapshot, snapshot_meta


def run_doctor(cfg: CitiesAIConfig | None = None) -> int:
    cfg = cfg or load_config()
    discovered = discover_paths()
    issues = 0

    print("CitiesAI doctor")
    print("===============")
    print(f"config: {config_path() if config_path().is_file() else '(not created - run citiesai setup)'}")
    print(f"discovery source: {discovered.source}")
    print("")

    game_dir = cfg.resolved_game_dir()
    locale_cok = cfg.resolved_locale_cok()
    export_path = cfg.resolved_export_path()

    print("[paths]")
    _check_path("game_dir", game_dir, must_exist=True, issues_ref=[issues])
    _check_path("locale_cok", locale_cok, must_exist=True, issues_ref=[issues])
    _check_path("export_path", export_path, must_exist=True, issues_ref=[issues])

    if export_path.is_file():
        snapshot = load_snapshot(export_path)
        meta = snapshot_meta(snapshot, path=export_path)
        print(f"  export schema: {meta.schema_version}")
        print(f"  export age: {meta.age_seconds / 60.0:.1f} min" if meta.age_seconds else "  export age: unknown")
        if meta.stale:
            print("  warning: export is stale (>11 min). Load city in-game or wait for next export cycle.")
            issues += 1
    print("")

    print("[knowledge]")
    try:
        reset_knowledge_cache()
        status = knowledge_status()
        print(f"  wiki chunks: {status['wiki_chunks']}")
        enc = status["encyclopedia"]
        print(f"  encyclopedia available: {enc.get('available')}")
        if not enc.get("available"):
            print(f"  encyclopedia note: {enc.get('warning', 'not found')}")
            issues += 1
    except Exception as exc:  # noqa: BLE001 - surface to user in doctor
        print(f"  error loading knowledge sources: {exc}")
        issues += 1
    print("")

    print("[llm]")
    llm = resolve_llm_settings(cfg)
    if llm:
        print(f"  provider: {cfg.llm_provider}")
        print(f"  model: {llm.model}")
        print(f"  api key: set via {llm.api_key_env}")
    else:
        print(f"  api key: not set ({cfg.llm_api_key_env})")
        print("  hint: free Mistral tier at https://console.mistral.ai (SMS verification)")
    print("")

    if issues:
        print(f"Result: {issues} issue(s) found.")
        return 1
    print("Result: OK")
    return 0


def _check_path(
    label: str,
    path: Path | None,
    *,
    must_exist: bool,
    issues_ref: list[int],
) -> None:
    if path is None:
        print(f"  {label}: missing")
        issues_ref[0] += 1
        return
    print(f"  {label}: {path}")
    if must_exist and not path.exists():
        print("    error: path does not exist")
        issues_ref[0] += 1
