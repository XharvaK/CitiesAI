from __future__ import annotations

from pathlib import Path

from .config import load_config, merge_discovered
from .discovery import discover_paths


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
