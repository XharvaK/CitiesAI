"""System tray integration for the native CitiesAI desktop app."""

from __future__ import annotations

import threading
from collections.abc import Callable
from io import BytesIO
from typing import TYPE_CHECKING

from PIL import Image
from pystray import Icon, Menu, MenuItem

if TYPE_CHECKING:
    from pystray import Icon as PystrayIcon


def _load_tray_icon() -> Image.Image:
    from importlib import resources

    try:
        data = resources.files("citiesai.gui.static").joinpath("logo.png").read_bytes()
        image = Image.open(BytesIO(data))
        return image.convert("RGBA")
    except OSError:
        return Image.new("RGBA", (64, 64), (30, 28, 22, 255))


class SystemTray:
    """Background tray icon with Open / Compact HUD / Exit menu."""

    def __init__(
        self,
        *,
        on_open: Callable[[], None],
        on_open_hud: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self._on_open = on_open
        self._on_open_hud = on_open_hud
        self._on_exit = on_exit
        self._icon: PystrayIcon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._icon is not None:
            return
        menu = Menu(
            MenuItem("Open CitiesAI", self._handle_open, default=True),
            MenuItem("Compact HUD", self._handle_open_hud),
            Menu.SEPARATOR,
            MenuItem("Exit", self._handle_exit),
        )
        self._icon = Icon("CitiesAI", _load_tray_icon(), "CitiesAI", menu)
        self._thread = threading.Thread(target=self._icon.run, name="citiesai-tray", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        icon = self._icon
        if icon is None:
            return
        self._icon = None
        try:
            icon.stop()
        except Exception:
            pass

    def _handle_open(self, _icon: PystrayIcon, _item: MenuItem) -> None:
        self._on_open()

    def _handle_open_hud(self, _icon: PystrayIcon, _item: MenuItem) -> None:
        self._on_open_hud()

    def _handle_exit(self, _icon: PystrayIcon, _item: MenuItem) -> None:
        self._on_exit()
