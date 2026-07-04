"""Generate CitiesAI.ico and sync logo.png into the GUI static bundle."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "packaging" / "assets" / "logo.png"
ICO_PATH = REPO / "packaging" / "assets" / "CitiesAI.ico"
STATIC_LOGO = REPO / "citiesai" / "gui" / "static" / "logo.png"
STATIC_FAVICON = REPO / "citiesai" / "gui" / "static" / "favicon.ico"

ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing source logo: {SOURCE}")

    img = Image.open(SOURCE).convert("RGBA")
    STATIC_LOGO.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, STATIC_LOGO)

    img.save(ICO_PATH, format="ICO", sizes=ICO_SIZES)
    shutil.copy2(ICO_PATH, STATIC_FAVICON)

    print(f"Wrote {ICO_PATH}")
    print(f"Synced {STATIC_LOGO}")
    print(f"Synced {STATIC_FAVICON}")


if __name__ == "__main__":
    main()
