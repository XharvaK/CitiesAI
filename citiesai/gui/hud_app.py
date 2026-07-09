"""CitiesAI Co-Mayor process entrypoint (PySide6 overlay)."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="citiesai-hud", description="CitiesAI Co-Mayor overlay")
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of the running CitiesAI GUI server (e.g. http://127.0.0.1:8765)",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Session token for authenticated Ask streaming",
    )
    args = parser.parse_args(argv)

    from .hud_window import run_comayor
    from .overlay import enable_dpi_awareness

    enable_dpi_awareness()
    return run_comayor(args.url, args.token)


if __name__ == "__main__":
    raise SystemExit(main())
