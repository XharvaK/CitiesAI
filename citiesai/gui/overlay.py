"""Win32 helpers for the CS2 telemetry HUD (top-center on game window)."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from typing import Any

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _gdi32 = ctypes.windll.gdi32
else:
    _user32 = None  # type: ignore[assignment]
    _gdi32 = None  # type: ignore[assignment]

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000

HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

MONITOR_DEFAULTTONEAREST = 2
MONITOR_DEFAULTTOPRIMARY = 1

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4

ISLAND_MARGIN_TOP = 12
MIN_ANCHOR_WIDTH = 200
MIN_ANCHOR_HEIGHT = 200

COMPACT_WIDTH_MIN = 180
COMPACT_WIDTH_MAX = 640
COMPACT_PILL_HEIGHT = 44

ASK_WIDTH_MIN = 360
ASK_WIDTH_MAX = 520
ASK_HEIGHT_MIN = 320
ASK_HEIGHT_MAX = 480

HUD_TITLE = "CitiesAI Co-Mayor"
HUD_BACKGROUND_COLOR = "#0c0b09"

# Stable signal-strip width: compact and Ask share the same horizontal footprint.
SIGNAL_STRIP_WIDTH = 460
ASK_PANEL_WIDTH = SIGNAL_STRIP_WIDTH
# Default / minimum expanded height; advisor may grow downward to fit content.
ADVISOR_PANEL_HEIGHT = 400
ADVISOR_PANEL_MIN_HEIGHT = ADVISOR_PANEL_HEIGHT
ASK_PANEL_HEIGHT = ADVISOR_PANEL_HEIGHT
ADVISOR_BOTTOM_MARGIN = 24

_HUD_TITLE_MARKERS = ("citiesai hud", "citiesai co-mayor", "citiesai island", "citiesai pulse")
_GAME_TITLE_MARKERS = ("cities: skylines", "cities skylines ii", "cities skylines 2")


class _POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


if sys.platform == "win32" and _user32 is not None:
    _WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    _MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(_RECT),
        ctypes.c_long,
    )
else:
    _WNDENUMPROC = None  # type: ignore[assignment,misc]
    _MONITORENUMPROC = None  # type: ignore[assignment,misc]


def clamp_compact_width(width: int) -> int:
    return max(COMPACT_WIDTH_MIN, min(COMPACT_WIDTH_MAX, int(width)))


def clamp_ask_width(width: int) -> int:
    return max(ASK_WIDTH_MIN, min(ASK_WIDTH_MAX, int(width)))


def clamp_ask_height(height: int) -> int:
    return max(ASK_HEIGHT_MIN, min(ASK_HEIGHT_MAX, int(height)))


def compact_window_size(pill_width: int, pill_height: int = COMPACT_PILL_HEIGHT) -> tuple[int, int]:
    return clamp_compact_width(pill_width), max(COMPACT_PILL_HEIGHT, int(pill_height))


def ask_window_size(width: int, height: int) -> tuple[int, int]:
    return clamp_ask_width(width), clamp_ask_height(height)


HUD_STATE_SIZES: dict[str, tuple[int, int]] = {
    "compact": compact_window_size(320),
    "advisor": ask_window_size(ASK_PANEL_WIDTH, ADVISOR_PANEL_HEIGHT),
    "ask": ask_window_size(ASK_PANEL_WIDTH, ASK_PANEL_HEIGHT),
}


def get_hwnd(window: Any) -> int | None:
    if sys.platform != "win32" or _user32 is None:
        return None
    try:
        native = getattr(window, "native", None)
        if native is None:
            return None
        handle = getattr(native, "Handle", None)
        if handle is None:
            return None
        return int(handle.ToInt32()) if hasattr(handle, "ToInt32") else int(handle)
    except Exception:
        return None


def _work_area_for_monitor(monitor: int) -> tuple[int, int, int, int] | None:
    if _user32 is None:
        return None
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    work = info.rcWork
    return work.left, work.top, work.right, work.bottom


def _primary_monitor_work_area() -> tuple[int, int, int, int] | None:
    if _user32 is None:
        return None
    monitor = _user32.MonitorFromWindow(0, MONITOR_DEFAULTTOPRIMARY)
    if not monitor:
        return None
    return _work_area_for_monitor(int(monitor))


def _foreground_hwnd() -> int:
    if _user32 is None:
        return 0
    return int(_user32.GetForegroundWindow() or 0)


def _window_title(hwnd: int) -> str:
    if _user32 is None or not hwnd:
        return ""
    length = int(_user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _is_hud_hwnd(hwnd: int) -> bool:
    title = _window_title(hwnd).lower()
    return any(marker in title for marker in _HUD_TITLE_MARKERS)


def get_client_rect_screen(hwnd: int) -> tuple[int, int, int, int] | None:
    if _user32 is None or not hwnd:
        return None
    client = _RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(client)):
        return None
    pt = _POINT(0, 0)
    if not _user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    return pt.x, pt.y, pt.x + client.right, pt.y + client.bottom


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    if _user32 is None:
        return 0, 0, 0, 0
    rect = _RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def _rect_size(rect: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = rect
    return max(0, right - left), max(0, bottom - top)


def _is_usable_anchor_rect(rect: tuple[int, int, int, int]) -> bool:
    width, height = _rect_size(rect)
    return width >= MIN_ANCHOR_WIDTH and height >= MIN_ANCHOR_HEIGHT


def _is_own_app_hwnd(hwnd: int) -> bool:
    title = _window_title(hwnd).lower()
    if _is_hud_hwnd(hwnd):
        return True
    return title.startswith("citiesai")


def enable_dpi_awareness() -> None:
    if sys.platform != "win32" or _user32 is None:
        return
    try:
        if hasattr(_user32, "SetProcessDpiAwarenessContext"):
            _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def prefers_reduced_motion() -> bool:
    """True when Windows client-area animations are disabled."""
    if sys.platform != "win32" or _user32 is None:
        return False
    SPI_GETCLIENTAREAANIMATION = 0x1042
    enabled = ctypes.c_int(1)
    try:
        ok = _user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION,
            0,
            ctypes.byref(enabled),
            0,
        )
    except Exception:
        return False
    if not ok:
        return False
    return int(enabled.value) == 0


def monitor_work_area_for_hwnd(hwnd: int) -> tuple[int, int, int, int] | None:
    if _user32 is None or not hwnd:
        return None
    monitor = int(_user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST))
    return _work_area_for_monitor(monitor)


def _find_game_hwnd() -> int:
    if sys.platform != "win32" or _user32 is None or _WNDENUMPROC is None:
        return 0
    fg = _foreground_hwnd()
    if fg:
        title = _window_title(fg).lower()
        if any(marker in title for marker in _GAME_TITLE_MARKERS):
            return fg
    matches: list[int] = []

    def _callback(hwnd: int, _lparam: int) -> bool:
        if not _user32.IsWindowVisible(hwnd):
            return True
        title = _window_title(int(hwnd)).lower()
        if any(marker in title for marker in _GAME_TITLE_MARKERS):
            matches.append(int(hwnd))
        return True

    _user32.EnumWindows(_WNDENUMPROC(_callback), 0)
    if not matches:
        return 0

    def _area(hwnd: int) -> int:
        w, h = _rect_size(get_window_rect(hwnd))
        return w * h

    return max(matches, key=_area)


def is_game_running() -> bool:
    return _find_game_hwnd() != 0


def find_hud_hwnds() -> list[int]:
    """Return visible Co-Mayor / HUD window handles (Win32 only)."""
    if sys.platform != "win32" or _user32 is None or _WNDENUMPROC is None:
        return []
    matches: list[int] = []

    def _callback(hwnd: int, _lparam: int) -> bool:
        if not _user32.IsWindowVisible(hwnd):
            return True
        if _is_hud_hwnd(int(hwnd)):
            matches.append(int(hwnd))
        return True

    _user32.EnumWindows(_WNDENUMPROC(_callback), 0)
    return matches


def close_orphan_hud_windows(*, exclude_pids: set[int] | None = None) -> int:
    """Best-effort close of Co-Mayor windows not owned by *exclude_pids*.

    Sends WM_CLOSE first, then terminates the process if the window remains.
    Never targets the current process PID. Returns the number of windows targeted.
    """
    if sys.platform != "win32" or _user32 is None:
        return 0
    keep = set(exclude_pids or set())
    keep.add(os.getpid())
    kernel32 = ctypes.windll.kernel32
    PROCESS_TERMINATE = 0x0001
    WM_CLOSE = 0x0010
    closed = 0
    for hwnd in find_hud_hwnds():
        pid = ctypes.c_ulong(0)
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        target_pid = int(pid.value)
        if target_pid in keep or target_pid <= 0:
            continue
        closed += 1
        try:
            _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass
        time.sleep(0.15)
        if not _user32.IsWindow(hwnd):
            continue
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, target_pid)
        if handle:
            try:
                kernel32.TerminateProcess(handle, 1)
            finally:
                kernel32.CloseHandle(handle)
    return closed


def anchor_rect(*, exclude_hwnd: int | None = None) -> tuple[int, int, int, int] | None:
    game = _find_game_hwnd()
    if game and game != exclude_hwnd:
        rect = get_window_rect(game)
        width, height = _rect_size(rect)
        if width < 900 or height < 500:
            if _user32 is not None:
                monitor = int(_user32.MonitorFromWindow(game, MONITOR_DEFAULTTONEAREST))
                work = _work_area_for_monitor(monitor)
                if work and _is_usable_anchor_rect(work):
                    return work
        if _is_usable_anchor_rect(rect):
            return rect
        client = get_client_rect_screen(game)
        if client and _is_usable_anchor_rect(client):
            return client
    for hwnd in (_foreground_hwnd(),):
        if not hwnd or hwnd == exclude_hwnd or _is_own_app_hwnd(hwnd):
            continue
        rect = get_window_rect(hwnd)
        if _is_usable_anchor_rect(rect):
            return rect
    return _primary_monitor_work_area()


def island_position_for_anchor(
    anchor: tuple[int, int, int, int],
    width: int,
    height: int,
    *,
    margin_top: int = ISLAND_MARGIN_TOP,
) -> tuple[int, int]:
    left, top, right, _bottom = anchor
    anchor_width = max(0, right - left)
    x = left + max(0, (anchor_width - width) // 2)
    y = top + margin_top
    return x, y


def _center_work_area(*, exclude_hwnd: int | None = None) -> tuple[int, int, int, int] | None:
    """Monitor work area used for top-center placement (game monitor, else primary)."""
    game = _find_game_hwnd()
    if game and game != exclude_hwnd:
        work = monitor_work_area_for_hwnd(game)
        if work and _is_usable_anchor_rect(work):
            return work
    return _primary_monitor_work_area()


def dynamic_island_position(
    width: int,
    height: int,
    *,
    exclude_hwnd: int | None = None,
) -> tuple[int, int]:
    # Always center on the monitor work area so the pill sits at true top-center,
    # not offset to a game client sub-rect or previous HWND size.
    work = _center_work_area(exclude_hwnd=exclude_hwnd)
    if work is not None:
        return island_position_for_anchor(work, int(width), int(height))
    rect = anchor_rect(exclude_hwnd=exclude_hwnd)
    if rect is None:
        return 100, 100
    return island_position_for_anchor(rect, int(width), int(height))


def place_window(
    hwnd: int,
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    activate: bool = False,
) -> None:
    if _user32 is None or not hwnd:
        return
    flags = SWP_SHOWWINDOW if activate else SWP_NOACTIVATE
    _user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        int(x),
        int(y),
        int(width),
        int(height),
        flags,
    )


def _region_corner_radius(state: str, width: int, height: int) -> int:
    """GDI CreateRoundRectRgn wants diameter-like corner args (width of ellipse)."""
    if state in ("advisor", "ask"):
        # ~22–28px visual radius → pass ~44–56 to GDI.
        return min(56, max(44, (height // 10) * 2), width // 4)
    # Compact capsule: full half-height ends.
    return max(2, height)


def apply_window_region(hwnd: int, width: int, height: int, *, state: str = "compact") -> None:
    if sys.platform != "win32" or _user32 is None or _gdi32 is None or not hwnd:
        return
    radius = _region_corner_radius(state, width, height)
    rgn = _gdi32.CreateRoundRectRgn(0, 0, int(width) + 1, int(height) + 1, radius, radius)
    if not rgn:
        return
    _user32.SetWindowRgn(hwnd, rgn, True)


def apply_overlay_styles(
    hwnd: int,
    width: int | None = None,
    height: int | None = None,
    *,
    state: str = "compact",
    interactive: bool = False,
) -> None:
    if sys.platform != "win32" or _user32 is None:
        return
    style = int(_user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
    if interactive:
        style &= ~WS_EX_NOACTIVATE
    else:
        style |= WS_EX_NOACTIVATE
    # Opaque window + SetWindowRgn clip. Do not use WS_EX_LAYERED for alpha.
    style &= ~WS_EX_LAYERED
    style &= ~0x00000020  # WS_EX_TRANSPARENT — keep mouse hits on the island
    _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    if width is not None and height is not None:
        apply_window_region(hwnd, width, height, state=state)
    raise_topmost(hwnd)


def raise_topmost(hwnd: int) -> None:
    if sys.platform != "win32" or _user32 is None:
        return
    _user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
    )


def place_island_window(
    hwnd: int,
    width: int,
    height: int,
    *,
    state: str = "compact",
    interactive: bool = False,
    exclude_hwnd: int | None = None,
) -> tuple[int, int, int, int]:
    requested_w, requested_h = int(width), int(height)
    x, y = dynamic_island_position(requested_w, requested_h, exclude_hwnd=exclude_hwnd)
    place_window(hwnd, x, y, requested_w, requested_h, activate=interactive)
    rect = get_window_rect(hwnd)
    aw, ah = _rect_size(rect)

    if state in ("advisor", "ask") and (ah < 300 or aw < 300):
        place_window(hwnd, x, y, requested_w, requested_h, activate=True)
        rect = get_window_rect(hwnd)
        aw, ah = _rect_size(rect)

    if aw > 0 and ah > 0:
        width, height = aw, ah
        x, y = dynamic_island_position(width, height, exclude_hwnd=exclude_hwnd)
        place_window(hwnd, x, y, width, height, activate=interactive)
    else:
        width, height = requested_w, requested_h

    apply_overlay_styles(hwnd, int(width), int(height), state=state, interactive=interactive)
    return int(x), int(y), int(width), int(height)


class HudOverlayController:
    """Keeps the HUD topmost and re-docked to top-center of the game window."""

    def __init__(
        self,
        window: Any,
        *,
        poll_interval: float = 0.5,
    ) -> None:
        self._window = window
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd: int | None = None
        self._last_size: tuple[int, int] = HUD_STATE_SIZES["compact"]
        self._last_state: str = "compact"
        self._interactive = False
        self._last_anchor: tuple[int, int, int, int] | None = None
        self._last_position: tuple[int, int] | None = None

    def set_size(
        self,
        width: int,
        height: int,
        *,
        state: str | None = None,
        interactive: bool | None = None,
    ) -> None:
        self._last_size = (width, height)
        if state is not None:
            self._last_state = state
        if interactive is not None:
            self._interactive = interactive

    @property
    def last_size(self) -> tuple[int, int]:
        return self._last_size

    @property
    def last_state(self) -> str:
        return self._last_state

    @property
    def interactive(self) -> bool:
        return self._interactive

    def apply_initial_styles(self) -> None:
        hwnd = get_hwnd(self._window)
        if hwnd is None:
            return
        self._hwnd = hwnd
        width, height = self._last_size
        x, y, width, height = place_island_window(
            hwnd,
            width,
            height,
            state=self._last_state,
            interactive=self._interactive,
            exclude_hwnd=hwnd,
        )
        self._last_size = (width, height)
        self._last_position = (x, y)

    def refresh_topmost(self) -> None:
        hwnd = self._hwnd or get_hwnd(self._window)
        if hwnd is not None:
            self._hwnd = hwnd
            raise_topmost(hwnd)

    def _redock(self, *, force: bool = False) -> None:
        width, height = self._last_size
        exclude = self._hwnd
        anchor = anchor_rect(exclude_hwnd=exclude)
        x, y = dynamic_island_position(width, height, exclude_hwnd=exclude)
        if (
            not force
            and anchor == self._last_anchor
            and (x, y) == self._last_position
            and self._last_size == (width, height)
        ):
            hwnd = self._hwnd or get_hwnd(self._window)
            if hwnd is not None:
                raise_topmost(hwnd)
            return
        self._last_anchor = anchor
        self._last_position = (x, y)
        try:
            hwnd = self._hwnd or get_hwnd(self._window)
            if hwnd is not None:
                x, y, width, height = place_island_window(
                    hwnd,
                    width,
                    height,
                    state=self._last_state,
                    interactive=self._interactive,
                    exclude_hwnd=self._hwnd,
                )
                self._last_size = (width, height)
                self._last_position = (x, y)
            else:
                self._window.resize(width, height)
                self._window.move(x, y)
        except Exception:
            pass
        hwnd = self._hwnd or get_hwnd(self._window)
        if hwnd is not None:
            raise_topmost(hwnd)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="citiesai-hud-overlay", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=1.0)

    def _loop(self) -> None:
        tick = 0
        while not self._stop.is_set():
            hwnd = self._hwnd or get_hwnd(self._window)
            if hwnd is None:
                self._stop.wait(self._poll_interval)
                continue
            self._hwnd = hwnd
            raise_topmost(hwnd)
            tick += 1
            if tick % 4 == 0:
                self._redock()
            self._stop.wait(self._poll_interval)
