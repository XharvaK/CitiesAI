from __future__ import annotations

from pathlib import Path

from .config import load_config, merge_discovered
from .discovery import discover_paths
from .llm import LLM_PRESETS


def apply_llm_provider(cfg, provider: str) -> None:
    preset = LLM_PRESETS.get(provider)
    if not preset:
        return
    cfg.llm_provider = provider
    cfg.llm_base_url = preset["base_url"]
    cfg.llm_api_key_env = preset["api_key_env"]
    cfg.llm_model = preset["model"]


def save_detected_config(
    *,
    path_overrides: dict[str, Path] | None = None,
    llm_model: str | None = None,
    llm_provider: str | None = None,
    llm_agentic_enabled: bool | None = None,
) -> Path:
    discovered = discover_paths()
    cfg = merge_discovered(load_config(), discovered)
    if path_overrides:
        if path_overrides.get("game_dir"):
            cfg.game_dir = path_overrides["game_dir"]
        if path_overrides.get("locale_cok"):
            cfg.locale_cok = path_overrides["locale_cok"]
        if path_overrides.get("export_path"):
            cfg.export_path = path_overrides["export_path"]
    if llm_provider:
        apply_llm_provider(cfg, llm_provider)
    if llm_model:
        cfg.llm_model = llm_model
    if llm_agentic_enabled is not None:
        cfg.llm_agentic_enabled = llm_agentic_enabled
    return cfg.write()


def run_setup(*, non_interactive: bool = False) -> int:
    discovered = discover_paths()
    cfg = merge_discovered(load_config(), discovered)

    print("CitiesAI setup")
    print("==============")
    print("")
    print("Detected paths:")
    print(f"  source: {discovered.source}")
    print(f"  game_dir: {discovered.game_dir or '(not found)'}")
    print(f"  locale_cok: {discovered.locale_cok or '(not found)'}")
    print(f"  export_path: {discovered.export_path}")
    print("")

    if not non_interactive:
        game_input = input(f"Game dir [{cfg.game_dir or ''}]: ").strip()
        if game_input:
            cfg.game_dir = Path(game_input)
        locale_input = input(f"Locale.cok [{cfg.locale_cok or ''}]: ").strip()
        if locale_input:
            cfg.locale_cok = Path(locale_input)
        export_input = input(f"Export path [{cfg.export_path or ''}]: ").strip()
        if export_input:
            cfg.export_path = Path(export_input)

        print("")
        print("LLM (optional - for citiesai ask without Cursor)")
        print("Recommended: Mistral free tier at https://console.mistral.ai")
        print("Set MISTRAL_API_KEY in your environment; it is never written to config.")
        model_input = input(f"LLM model [{cfg.llm_model}]: ").strip()
        if model_input:
            cfg.llm_model = model_input

    if non_interactive:
        written = save_detected_config()
    else:
        written = cfg.write()
    print("")
    print(f"Wrote config: {written}")
    print("")
    print("Next steps:")
    print("  1. Install CS2 Data Export mod (see docs/INSTALL-MOD.md)")
    print("  2. Load a city in-game")
    print("  3. Set MISTRAL_API_KEY (optional) and run: citiesai doctor")
    print('  4. Ask: citiesai ask "what should I build first?"')
    return 0
