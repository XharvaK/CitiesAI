"""Desktop entry point for packaged CitiesAI builds."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "--hud-process":
        # Co-Mayor child process: CitiesAI.exe --hud-process --url ... --token ...
        from citiesai.gui.hud_app import main as hud_main

        return hud_main(args[1:])

    parser = argparse.ArgumentParser(prog="CitiesAI", add_help=True)
    parser.add_argument(
        "--hud",
        action="store_true",
        help="Also open Co-Mayor overlay",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parsed, _unknown = parser.parse_known_args(args)

    from citiesai.gui.server import run_gui

    return run_gui(host=parsed.host, port=parsed.port, hud=parsed.hud)


if __name__ == "__main__":
    raise SystemExit(main())
