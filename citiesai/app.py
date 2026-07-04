"""Desktop entry point for packaged CitiesAI builds."""

from citiesai.gui.server import run_gui

if __name__ == "__main__":
    raise SystemExit(run_gui())
