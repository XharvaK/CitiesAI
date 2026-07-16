"""PySide6 Co-Mayor overlay: municipal signal strip + evidence-first advisor."""

from __future__ import annotations

import html
import sys
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QThread,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRegion,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .hud_client import ask_stream, fetch_hud, focus_main
from .overlay import (
    ADVISOR_BOTTOM_MARGIN,
    ADVISOR_PANEL_HEIGHT,
    ADVISOR_PANEL_MIN_HEIGHT,
    ASK_PANEL_HEIGHT,
    COMPACT_PILL_HEIGHT,
    HUD_BACKGROUND_COLOR,
    SIGNAL_STRIP_WIDTH,
    _find_game_hwnd,
    get_window_rect,
    prefers_reduced_motion,
    raise_topmost,
)

# Matte municipal palette (aligned with dashboard Sätteri ink, near-black shell).
HUD_BG = QColor(HUD_BACKGROUND_COLOR)
HUD_SURFACE = QColor("#14120e")
HUD_ELEVATED = QColor("#1a1711")
HUD_TEXT = QColor("#f2ead3")
HUD_BODY = QColor("#d8d0be")
HUD_MUTED = QColor("#9a9080")
HUD_SEPARATOR = QColor("#3a342a")
HUD_OK = QColor("#8faa7a")
HUD_WARN = QColor("#c4a05a")
HUD_BAD = QColor("#b53737")
HUD_HAIRLINE = QColor(58, 52, 42, 230)
HUD_HIGHLIGHT = QColor(242, 234, 211, 14)
HUD_OLIVE = QColor("#a8ad78")
HUD_OLIVE_MUTED = QColor("#737654")
HUD_OLIVE_SURFACE = QColor("#202116")

POLL_MS = 10000
EXPAND_MS = 220
COLLAPSE_MS = 180
BODY_FADE_MS = 120
CYCLE_SLIDE_MS = 200
CYCLE_MS = 10_000
TOKEN_PAINT_MS = 50
SHELL_RADIUS = 6.0
ASK_RADIUS = 8.0

_FONT_FAMILIES: dict[str, str] | None = None


def _load_packaged_fonts() -> dict[str, str]:
    """Return the UI font families used by Co-Mayor (Segoe UI, no mono)."""
    global _FONT_FAMILIES
    if _FONT_FAMILIES is not None:
        return _FONT_FAMILIES
    families = {
        "sans": "Segoe UI",
        "mono": "Segoe UI",
    }
    _FONT_FAMILIES = families
    return families


def _grade_color(grade: str | None) -> QColor:
    letter = (grade or "").strip().upper()[:1]
    return {
        "A": HUD_OK,
        "B": QColor("#b5ab95"),
        "C": HUD_WARN,
        "D": QColor("#d4956a"),
        "F": HUD_BAD,
    }.get(letter, HUD_MUTED)


def _severity_color(severity: str | None) -> QColor:
    if severity == "error":
        return HUD_BAD
    if severity == "warn":
        return HUD_WARN
    if severity is None:
        return HUD_MUTED
    return HUD_OK


def _severity_label(severity: str | None) -> str:
    return {
        "error": "CRIT",
        "warn": "ATTN",
        "info": "INFO",
    }.get(str(severity or ""), "")


def _rgba(color: QColor, alpha: float) -> str:
    a = max(0, min(255, int(round(alpha * 255))))
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {a / 255:.3f})"


def _advisor_list_html(items: list[Any], *, empty: str) -> str:
    rows = [str(item).strip() for item in items if str(item).strip()]
    if not rows:
        return f'<p style="margin:0;color:{HUD_MUTED.name()};font-size:11px;">{html.escape(empty)}</p>'
    lis = "".join(
        f'<li style="margin:0 0 4px;">{html.escape(row)}</li>' for row in rows
    )
    return (
        f'<ul style="margin:0;padding-left:16px;color:{HUD_BODY.name()};'
        f'font-size:11px;line-height:1.45;">{lis}</ul>'
    )


def _advisor_evidence_html(evidence: list[Any]) -> str:
    rows: list[str] = []
    for item in evidence:
        if isinstance(item, dict):
            label = str(item.get("label") or "Evidence").strip()
            value = str(item.get("value") or "").strip()
            if not value:
                continue
            rows.append(
                f"<li><strong>{html.escape(label)}:</strong> {html.escape(value)}</li>"
            )
        else:
            text = str(item).strip()
            if text:
                rows.append(f"<li>{html.escape(text)}</li>")
    if not rows:
        return (
            f'<p style="margin:0;color:{HUD_MUTED.name()};font-size:11px;">'
            "No structured evidence.</p>"
        )
    return (
        f'<ul style="margin:0;padding-left:16px;color:{HUD_BODY.name()};'
        f'font-size:11px;line-height:1.45;">{"".join(rows)}</ul>'
    )


def _markdown_lite_to_html(text: str) -> str:
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    with_breaks = escaped.replace("\n\n", "</p><p>").replace("\n", "<br>")
    parts: list[str] = []
    i = 0
    while i < len(with_breaks):
        start = with_breaks.find("**", i)
        if start < 0:
            parts.append(with_breaks[i:])
            break
        end = with_breaks.find("**", start + 2)
        if end < 0:
            parts.append(with_breaks[i:])
            break
        parts.append(with_breaks[i:start])
        parts.append(f"<strong>{with_breaks[start + 2 : end]}</strong>")
        i = end + 2
    return (
        f'<div style="line-height:1.55;color:{HUD_BODY.name()};">'
        f"<p>{''.join(parts)}</p></div>"
    )


class AskWorker(QThread):
    event_received = Signal(str, object)
    finished_ok = Signal()

    def __init__(
        self,
        base_url: str,
        token: str,
        question: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._base_url = base_url
        self._token = token
        self._question = question
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        def on_event(event: str, payload: dict[str, Any]) -> None:
            self.event_received.emit(event, payload)

        ask_stream(
            self._base_url,
            self._token,
            self._question,
            on_event=on_event,
            should_abort=lambda: self._abort,
        )
        self.finished_ok.emit()


class IssueButton(QWidget):
    """Focusable issue control (keyboard + click) hosting the severity rail and title."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("issueBtn")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._enabled_click = True

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        self._enabled_click = enabled

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if (
            self._enabled_click
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(point)
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._enabled_click and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class CoMayorWindow(QWidget):
    """Frameless municipal signal strip with an integrated Ask drawer."""

    def __init__(self, base_url: str, token: str) -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._mode = "compact"
        self._priorities: list[dict[str, Any]] = []
        self._cycle_index = 0
        self._last_priority: dict[str, Any] | None = None
        self._displayed_priority_id: str | None = None
        self._last_hud_ok = True
        self._ask_worker: AskWorker | None = None
        self._ask_busy = False
        self._transcript: list[tuple[str, str]] = []
        self._export_stale = False
        self._thinking = False
        self._think_step = 0
        self._animating = False
        self._sliding = False
        self._header_hovered = False
        self._pending_expand: dict[str, Any] | None = None
        self._shell_radius = SHELL_RADIUS
        self._strip_width = SIGNAL_STRIP_WIDTH
        self._reduce_motion = prefers_reduced_motion()
        self._token_dirty = False
        self._prio_active_is_a = True

        self.setWindowTitle("CitiesAI Co-Mayor")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(self._strip_width)

        self._shell = QFrame(self)
        self._shell.setObjectName("shell")
        self._shell.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._shell)

        shell_layout = QVBoxLayout(self._shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self._build_header()
        self._build_ask_body()
        shell_layout.addWidget(self._header)
        shell_layout.addWidget(self._ask_body, stretch=1)
        self._ask_body.setVisible(False)
        self._ask_body.setMaximumHeight(0)
        self._show_panel("advisor")

        self._body_opacity = QGraphicsOpacityEffect(self._ask_body)
        self._body_opacity.setOpacity(0.0)
        self._ask_body.setGraphicsEffect(self._body_opacity)

        self._geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._geo_anim.finished.connect(self._on_geo_finished)

        self._body_fade = QPropertyAnimation(self._body_opacity, b"opacity", self)
        self._body_fade.setDuration(BODY_FADE_MS)
        self._body_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._slide_out = QPropertyAnimation(self._prio_label_a, b"pos", self)
        self._slide_in = QPropertyAnimation(self._prio_label_b, b"pos", self)
        self._fade_out = QPropertyAnimation(self._prio_fx_a, b"opacity", self)
        self._fade_in = QPropertyAnimation(self._prio_fx_b, b"opacity", self)
        for anim in (self._slide_out, self._slide_in, self._fade_out, self._fade_in):
            anim.setDuration(CYCLE_SLIDE_MS)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_in.finished.connect(self._on_slide_finished)

        self._stale_pulse = QVariantAnimation(self)
        self._stale_pulse.setStartValue(0.45)
        self._stale_pulse.setEndValue(1.0)
        self._stale_pulse.setDuration(900)
        self._stale_pulse.setLoopCount(-1)
        self._stale_pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._stale_pulse.valueChanged.connect(self._on_stale_pulse)

        self._think_timer = QTimer(self)
        self._think_timer.setInterval(380)
        self._think_timer.timeout.connect(self._tick_thinking)

        self._cycle_timer = QTimer(self)
        self._cycle_timer.setInterval(CYCLE_MS)
        self._cycle_timer.timeout.connect(self._advance_priority_cycle)

        self._token_paint = QTimer(self)
        self._token_paint.setInterval(TOKEN_PAINT_MS)
        self._token_paint.timeout.connect(self._flush_token_paint)

        self._apply_stylesheet()
        self._place_compact(animate=False)

        self._poll = QTimer(self)
        self._poll.timeout.connect(self.refresh)
        self._poll.start(POLL_MS)
        QTimer.singleShot(50, self.refresh)

        self._topmost = QTimer(self)
        self._topmost.timeout.connect(self._ensure_topmost)
        self._topmost.start(2000)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget {{
                color: {HUD_TEXT.name()};
                font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
                font-size: 11px;
            }}
            QLabel#grade {{
                font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 0.02em;
                border: none;
                border-radius: 4px;
                background: {HUD_ELEVATED.name()};
                min-width: 26px;
                max-width: 26px;
                min-height: 26px;
                max-height: 26px;
                qproperty-alignment: AlignCenter;
            }}
            QPushButton#grade {{
                font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 0.02em;
                border: none;
                border-radius: 4px;
                background: {HUD_ELEVATED.name()};
                color: {HUD_TEXT.name()};
                min-width: 26px;
                max-width: 26px;
                min-height: 26px;
                max-height: 26px;
                padding: 0;
            }}
            QPushButton#grade:hover {{
                background: {_rgba(HUD_TEXT, 0.08)};
            }}
            QPushButton#grade:focus-visible {{
                border: 1px solid {_rgba(HUD_TEXT, 0.4)};
            }}
            QWidget#issueBtn {{
                border: none;
                background: transparent;
                border-radius: 4px;
            }}
            QWidget#issueBtn:hover {{
                background: {_rgba(HUD_TEXT, 0.05)};
            }}
            QWidget#issueBtn:focus {{
                border: 1px solid {_rgba(HUD_TEXT, 0.4)};
            }}
            QWidget#issueBtn:disabled {{
                background: transparent;
            }}
            QFrame#severityRail {{
                border: none;
                border-radius: 1px;
                min-width: 3px;
                max-width: 3px;
                background: {HUD_MUTED.name()};
            }}
            QLabel#priorityText {{
                background: transparent;
                border: none;
                color: {HUD_TEXT.name()};
                font-weight: 500;
                font-size: 11px;
                padding: 0 2px;
            }}
            QLabel#cyclePager, QLabel#freshLabel {{
                font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 0.06em;
                color: {HUD_MUTED.name()};
                qproperty-alignment: AlignCenter;
            }}
            QLabel#cyclePager {{
                min-width: 24px;
            }}
            QLabel#freshLabel {{
                min-width: 36px;
            }}
            QFrame#askDivider {{
                max-height: 1px;
                min-height: 1px;
                border: none;
                background: {HUD_SEPARATOR.name()};
            }}
            QPushButton#sendBtn {{
                border: none;
                background: {HUD_ELEVATED.name()};
                color: {HUD_MUTED.name()};
                font-size: 13px;
                font-weight: 600;
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
                border-radius: 8px;
            }}
            QPushButton#sendBtn:enabled {{
                background: #2a261e;
                color: {HUD_TEXT.name()};
            }}
            QPushButton#sendBtn:enabled:hover {{
                background: #353028;
            }}
            QPushButton#sendBtn:focus-visible {{
                border: 1px solid {_rgba(HUD_TEXT, 0.4)};
            }}
            QPushButton#sendBtn:disabled {{
                background: {HUD_ELEVATED.name()};
                color: rgba(154,144,128,0.45);
            }}
            QPushButton#backBtn {{
                background: #2a261e;
                border: 1px solid {HUD_SEPARATOR.name()};
                border-radius: 8px;
                padding: 9px 12px;
                font-size: 12px;
                font-weight: 650;
                color: {HUD_TEXT.name()};
            }}
            QPushButton#backBtn:hover {{
                background: #353028;
            }}
            QPushButton#backBtn:pressed {{
                background: {HUD_ELEVATED.name()};
            }}
            QPushButton#backBtn:focus-visible {{
                border: 1px solid {_rgba(HUD_TEXT, 0.4)};
            }}
            QPushButton#askFollowBtn {{
                background: {HUD_OLIVE_SURFACE.name()};
                border: 1px solid {HUD_OLIVE_MUTED.name()};
                border-radius: 8px;
                padding: 9px 12px;
                font-size: 12px;
                font-weight: 650;
                color: {HUD_TEXT.name()};
            }}
            QPushButton#askFollowBtn:hover {{
                background: #2a2c1c;
            }}
            QPushButton#askFollowBtn:focus-visible {{
                border: 1px solid {_rgba(HUD_TEXT, 0.4)};
            }}
            QLineEdit#askInput {{
                background: {HUD_ELEVATED.name()};
                border: 1px solid {HUD_SEPARATOR.name()};
                border-radius: 8px;
                padding: 7px 12px;
                min-height: 16px;
                color: {HUD_TEXT.name()};
                selection-background-color: #353028;
            }}
            QLineEdit#askInput:focus {{
                border: 1px solid {_rgba(HUD_TEXT, 0.35)};
                background: #1e1b14;
            }}
            QTextBrowser#thread, QTextBrowser#advisorBrief {{
                background: transparent;
                border: none;
                color: {HUD_BODY.name()};
                padding: 4px 0 2px;
            }}
            QTextBrowser#thread QScrollBar:vertical {{
                width: 4px;
                background: transparent;
                margin: 2px 0;
            }}
            QTextBrowser#advisorBrief QScrollBar:vertical {{
                width: 8px;
                background: transparent;
                margin: 2px 0;
            }}
            QTextBrowser#thread QScrollBar::handle:vertical {{
                background: rgba(58, 52, 42, 0.7);
                border-radius: 2px;
                min-height: 20px;
            }}
            QTextBrowser#advisorBrief QScrollBar::handle:vertical {{
                background: {_rgba(HUD_MUTED, 0.55)};
                border-radius: 4px;
                min-height: 24px;
            }}
            QTextBrowser#thread QScrollBar::add-line:vertical,
            QTextBrowser#thread QScrollBar::sub-line:vertical,
            QTextBrowser#advisorBrief QScrollBar::add-line:vertical,
            QTextBrowser#advisorBrief QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            """
        )

    def _build_header(self) -> None:
        self._header = QWidget()
        self._header.setObjectName("signalHeader")
        self._header.setFixedHeight(COMPACT_PILL_HEIGHT)
        row = QHBoxLayout(self._header)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._grade = QPushButton("—")
        self._grade.setObjectName("grade")
        self._grade.setCursor(Qt.CursorShape.PointingHandCursor)
        self._grade.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._grade.setAccessibleName("Open CitiesAI dashboard")
        self._grade.setToolTip("Open CitiesAI dashboard")
        self._grade.clicked.connect(self._on_grade_click)
        row.addWidget(self._grade, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._issue_btn = IssueButton()
        self._issue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._issue_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._issue_btn.setFixedHeight(28)
        self._issue_btn.clicked.connect(self._on_priority_click)
        self._issue_btn.setAccessibleName("Current city issue")

        issue_row = QHBoxLayout(self._issue_btn)
        issue_row.setContentsMargins(6, 0, 6, 0)
        issue_row.setSpacing(8)
        issue_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._severity_rail = QFrame()
        self._severity_rail.setObjectName("severityRail")
        self._severity_rail.setFixedHeight(16)
        issue_row.addWidget(self._severity_rail, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._prio_stack = QWidget()
        self._prio_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._prio_stack.setFixedHeight(28)

        self._prio_label_a = QLabel("No export")
        self._prio_label_a.setObjectName("priorityText")
        self._prio_label_a.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._prio_label_a.setWordWrap(False)
        self._prio_label_b = QLabel("")
        self._prio_label_b.setObjectName("priorityText")
        self._prio_label_b.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._prio_label_b.setWordWrap(False)
        self._prio_label_a.setParent(self._prio_stack)
        self._prio_label_b.setParent(self._prio_stack)
        self._prio_label_a.setGeometry(0, 0, 200, 28)
        self._prio_label_b.setGeometry(0, 28, 200, 28)

        self._prio_fx_a = QGraphicsOpacityEffect(self._prio_label_a)
        self._prio_fx_a.setOpacity(1.0)
        self._prio_label_a.setGraphicsEffect(self._prio_fx_a)
        self._prio_fx_b = QGraphicsOpacityEffect(self._prio_label_b)
        self._prio_fx_b.setOpacity(0.0)
        self._prio_label_b.setGraphicsEffect(self._prio_fx_b)

        issue_row.addWidget(self._prio_stack, stretch=1)
        row.addWidget(self._issue_btn, stretch=1, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._cycle_pager = QLabel("")
        self._cycle_pager.setObjectName("cyclePager")
        self._cycle_pager.setVisible(False)
        self._cycle_pager.setAccessibleName("Issue pager")
        row.addWidget(self._cycle_pager, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._fresh = QLabel("LIVE")
        self._fresh.setObjectName("freshLabel")
        self._fresh.setStyleSheet(f"color: {HUD_OK.name()};")
        self._fresh.setAccessibleName("Export freshness")
        row.addWidget(self._fresh, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._header.installEventFilter(self)
        self._issue_btn.installEventFilter(self)

    def _build_ask_body(self) -> None:
        self._ask_body = QWidget()
        self._ask_body.setObjectName("askBody")
        col = QVBoxLayout(self._ask_body)
        col.setContentsMargins(12, 0, 12, 10)
        col.setSpacing(6)

        self._ask_divider = QFrame()
        self._ask_divider.setObjectName("askDivider")
        col.addWidget(self._ask_divider)

        self._panel_stack = QStackedWidget()
        self._panel_stack.setObjectName("panelStack")

        advisor_page = QWidget()
        advisor_col = QVBoxLayout(advisor_page)
        advisor_col.setContentsMargins(0, 0, 0, 0)
        advisor_col.setSpacing(8)

        self._advisor_brief = QTextBrowser()
        self._advisor_brief.setObjectName("advisorBrief")
        self._advisor_brief.setOpenExternalLinks(False)
        self._advisor_brief.setReadOnly(True)
        self._advisor_brief.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._advisor_brief.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._advisor_brief.document().setDocumentMargin(0)
        self._advisor_brief.setAccessibleName("Issue advisor brief")
        advisor_col.addWidget(self._advisor_brief, stretch=1)

        self._ask_follow_btn = QPushButton("Ask follow-up")
        self._ask_follow_btn.setObjectName("askFollowBtn")
        self._ask_follow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ask_follow_btn.setAccessibleName("Ask follow-up")
        self._ask_follow_btn.clicked.connect(self._enter_ask_follow_up)
        advisor_col.addWidget(self._ask_follow_btn)

        ask_page = QWidget()
        ask_col = QVBoxLayout(ask_page)
        ask_col.setContentsMargins(0, 0, 0, 0)
        ask_col.setSpacing(6)

        self._thread = QTextBrowser()
        self._thread.setObjectName("thread")
        self._thread.setOpenExternalLinks(False)
        self._thread.setReadOnly(True)
        self._thread.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._thread.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._thread.document().setDocumentMargin(0)
        self._thread.setAccessibleName("Advisor conversation")
        ask_col.addWidget(self._thread, stretch=1)

        compose = QHBoxLayout()
        compose.setContentsMargins(0, 2, 0, 0)
        compose.setSpacing(6)
        self._send_btn = QPushButton("↑")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.setEnabled(False)
        self._send_btn.setAccessibleName("Send follow-up")
        self._send_btn.clicked.connect(self._on_send)
        self._input = QLineEdit()
        self._input.setObjectName("askInput")
        self._input.setPlaceholderText("Follow up…")
        self._input.setAccessibleName("Follow-up question")
        self._input.returnPressed.connect(self._on_send)
        self._input.textChanged.connect(self._on_input_changed)
        compose.addWidget(self._input, stretch=1)
        compose.addWidget(self._send_btn)
        ask_col.addLayout(compose)

        self._panel_stack.addWidget(advisor_page)
        self._panel_stack.addWidget(ask_page)
        col.addWidget(self._panel_stack, stretch=1)

        self._back_btn = QPushButton("Back to game")
        self._back_btn.setObjectName("backBtn")
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setAccessibleName("Back to game")
        self._back_btn.clicked.connect(self.collapse_to_compact)
        col.addWidget(self._back_btn)

    def _show_panel(self, which: str) -> None:
        self._panel_stack.setCurrentIndex(0 if which == "advisor" else 1)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj in (self._header, self._issue_btn):
            et = event.type()
            if et == QEvent.Type.Enter:
                self._header_hovered = True
                self._sync_cycle_timer()
            elif et == QEvent.Type.Leave:
                # Leave may fire when moving between header children; re-check.
                under = self._header.underMouse() or self._issue_btn.underMouse()
                self._header_hovered = under
                self._sync_cycle_timer()
        return super().eventFilter(obj, event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = self._shell_radius
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        fill = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        fill.setColorAt(0.0, QColor(26, 23, 17))
        fill.setColorAt(0.14, HUD_BG)
        fill.setColorAt(1.0, HUD_BG)
        painter.fillPath(path, fill)

        painter.setPen(QPen(HUD_HAIRLINE, 1.0))
        painter.drawPath(path)

        highlight = QPainterPath()
        top = rect.adjusted(10, 1, -10, 0)
        highlight.moveTo(top.left(), top.top() + 1)
        highlight.lineTo(top.right(), top.top() + 1)
        painter.setPen(QPen(HUD_HIGHLIGHT, 1.0))
        painter.drawPath(highlight)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and (
            self._mode in ("advisor", "ask") or self._animating
        ):
            if self._mode == "ask" and not self._animating:
                self._return_to_advisor()
            else:
                self.collapse_to_compact()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._stop_stale_pulse()
        self._stop_thinking()
        if self._token_paint.isActive():
            self._token_paint.stop()
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_priority_labels()

    def _hwnd(self) -> int | None:
        try:
            return int(self.winId())
        except Exception:
            return None

    def _ensure_topmost(self) -> None:
        hwnd = self._hwnd()
        if hwnd:
            raise_topmost(hwnd)

    def _target_rect(self, width: int, height: int) -> QRect:
        """Top-center on the monitor work area using Qt logical coordinates."""
        screen = QGuiApplication.primaryScreen()
        try:
            game = _find_game_hwnd()
            if game:
                rect = get_window_rect(game)
                if rect is not None:
                    left, top, right, bottom = rect
                    for candidate in QGuiApplication.screens():
                        dpr = float(candidate.devicePixelRatio()) or 1.0
                        geo = candidate.geometry()
                        phys = QRect(
                            int(geo.x() * dpr),
                            int(geo.y() * dpr),
                            int(geo.width() * dpr),
                            int(geo.height() * dpr),
                        )
                        cx = (left + right) // 2
                        cy = (top + bottom) // 2
                        if phys.contains(cx, cy):
                            screen = candidate
                            break
        except Exception:
            pass
        if screen is None:
            return QRect(100, 12, width, height)
        geo = screen.availableGeometry()
        x = geo.x() + max(0, (geo.width() - int(width)) // 2)
        y = geo.y() + 12
        return QRect(x, y, int(width), int(height))

    def _abort_geometry_anim(self) -> None:
        if self._geo_anim.state() == QPropertyAnimation.State.Running:
            self._geo_anim.stop()
        if self._body_fade.state() == QPropertyAnimation.State.Running:
            self._body_fade.stop()
        self._animating = False
        self._geo_on_done = None

    def _animate_height(
        self,
        height: int,
        *,
        duration: int,
        activate: bool,
        easing: QEasingCurve.Type,
        on_done: Any | None = None,
    ) -> None:
        self._abort_geometry_anim()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        width = self._strip_width
        target = self._target_rect(width, height)
        self._animating = True
        self._geo_on_done = on_done
        self._geo_target = target
        self._geo_activate = activate
        self._shell_radius = ASK_RADIUS if height > COMPACT_PILL_HEIGHT else SHELL_RADIUS
        if self._reduce_motion or duration <= 0:
            self.setGeometry(target)
            self.setFixedSize(width, height)
            self._on_geo_finished()
            return
        self._geo_anim.setEasingCurve(easing)
        self._geo_anim.setDuration(duration)
        self._geo_anim.setStartValue(self.geometry())
        self._geo_anim.setEndValue(target)
        if activate:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self._geo_anim.start()

    def _on_geo_finished(self) -> None:
        target = getattr(self, "_geo_target", None)
        if target is not None:
            width, height = target.width(), target.height()
            target = self._target_rect(width, height)
            self.setGeometry(target)
            self.setFixedSize(width, height)
        self._animating = False
        if getattr(self, "_geo_activate", False):
            self.activateWindow()
            self.raise_()
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._ensure_topmost()
        self.update()
        on_done = getattr(self, "_geo_on_done", None)
        self._geo_on_done = None
        if on_done:
            on_done()

    def _fade_ask_body(self, *, to_visible: bool) -> None:
        if self._reduce_motion:
            self._body_opacity.setOpacity(1.0 if to_visible else 0.0)
            return
        self._body_fade.stop()
        self._body_fade.setStartValue(self._body_opacity.opacity())
        self._body_fade.setEndValue(1.0 if to_visible else 0.0)
        self._body_fade.start()

    def _place(self, width: int, height: int, *, activate: bool = False) -> None:
        target = self._target_rect(width, height)
        self.setFixedSize(width, height)
        self.setGeometry(target)
        if activate:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            self.activateWindow()
            self.raise_()
        else:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._ensure_topmost()
        self.update()

    def _place_compact(self, *, animate: bool = False) -> None:
        self._shell_radius = SHELL_RADIUS
        if animate and self.isVisible() and not self._reduce_motion:
            self._animate_height(
                COMPACT_PILL_HEIGHT,
                duration=COLLAPSE_MS,
                activate=False,
                easing=QEasingCurve.Type.InCubic,
            )
        else:
            self._place(self._strip_width, COMPACT_PILL_HEIGHT, activate=False)

    def _layout_priority_labels(self) -> None:
        w = max(40, self._prio_stack.width())
        h = self._prio_stack.height() or 28
        self._prio_stack.setMask(QRegion(0, 0, w, h))
        active = self._prio_label_a if self._prio_active_is_a else self._prio_label_b
        idle = self._prio_label_b if self._prio_active_is_a else self._prio_label_a
        if not self._sliding:
            active.setGeometry(0, 0, w, h)
            idle.setGeometry(0, h, w, h)

    def _elide_priority_title(self, title: str) -> str:
        available = max(40, self._prio_stack.width() - 4)
        if available < 40:
            return title
        fm = self._prio_label_a.fontMetrics()
        return fm.elidedText(title, Qt.TextElideMode.ElideRight, available)

    def refresh(self) -> None:
        if self._animating:
            return
        data = fetch_hud(self._base_url)
        ok = bool(data.get("ok"))
        self._last_hud_ok = ok
        if not ok:
            self._priorities = []
            self._cycle_index = 0
            # Keep the open advisor/ask brief when a poll briefly goes offline.
            if self._mode not in ("advisor", "ask"):
                self._last_priority = None
                self._update_priority(None, animate=False)
            self._sync_cycle_timer()
            self._stop_stale_pulse()
            self._export_stale = False
            self._fresh.setText("OFF")
            self._fresh.setStyleSheet(f"color: {HUD_MUTED.name()};")
            self._fresh.setToolTip("Export unavailable")
            self._grade.setText("—")
            self._grade.setStyleSheet("")
            self._grade.setToolTip("Grade unavailable — open CitiesAI dashboard")
        else:
            grade = (data.get("report_card") or {}).get("overall_grade")
            self._grade.setText(str(grade) if grade else "—")
            color = _grade_color(str(grade) if grade else None)
            self._grade.setStyleSheet(
                f"QPushButton#grade {{ color: {color.name()}; "
                f"background: {_rgba(color, 0.14)}; "
                f"border: none; border-radius: 4px; font-weight: 700; }}"
            )
            tip = f"Grade {grade} — open CitiesAI dashboard" if grade else "Open CitiesAI dashboard"
            self._grade.setToolTip(tip)

            raw = data.get("priorities")
            priorities: list[dict[str, Any]] = []
            if isinstance(raw, list):
                for item in raw[:3]:
                    if isinstance(item, dict) and item.get("title"):
                        priorities.append(item)
            if not priorities:
                top = data.get("top_priority")
                if isinstance(top, dict) and top.get("title"):
                    priorities = [top]

            self._apply_priorities(priorities)

            meta = data.get("meta") or {}
            stale = bool(meta.get("stale"))
            self._set_stale(stale)

        if self._mode == "compact" and not self._animating:
            if self.height() != COMPACT_PILL_HEIGHT or self.width() != self._strip_width:
                self._place_compact(animate=False)

    def _apply_priorities(self, priorities: list[dict[str, Any]]) -> None:
        current_id = None
        if self._priorities and 0 <= self._cycle_index < len(self._priorities):
            current_id = str(self._priorities[self._cycle_index].get("id") or "")
        if self._mode in ("advisor", "ask") and self._last_priority:
            current_id = str(self._last_priority.get("id") or current_id or "")

        self._priorities = priorities
        if current_id:
            for idx, item in enumerate(self._priorities):
                if str(item.get("id") or "") == current_id:
                    self._cycle_index = idx
                    break
            else:
                self._cycle_index = 0
                if self._mode in ("advisor", "ask"):
                    self._handle_priority_resolved(current_id)
                    return
        else:
            self._cycle_index = 0

        shown = self._current_priority()
        self._last_priority = shown
        self._update_priority(shown, animate=self._mode == "compact")
        if self._mode == "advisor" and shown:
            self._render_advisor_brief(shown)
        self._sync_cycle_timer()

    def _handle_priority_resolved(self, resolved_id: str) -> None:
        """Keep expanded geometry stable when the open priority leaves the queue."""
        shown = self._current_priority()
        if shown:
            self._last_priority = shown
            self._update_priority(shown, animate=False)
            if self._mode == "ask":
                self._abort_ask()
                self._stop_thinking()
                self._transcript.clear()
                self._thread.clear()
                self._set_ask_busy(False)
                self._mode = "advisor"
                self._show_panel("advisor")
            self._render_advisor_brief(shown)
            note = (
                f'<p style="margin:8px 0 0;color:{HUD_WARN.name()};font-size:11px;">'
                f"Previous priority ({html.escape(resolved_id)}) left the queue — "
                "showing the next item.</p>"
            )
            self._advisor_brief.setHtml(self._advisor_brief.toHtml() + note)
        else:
            self._last_priority = None
            self._update_priority(None, animate=False)
            if self._mode != "compact":
                self.collapse_to_compact()
        self._sync_cycle_timer()

    def _current_priority(self) -> dict[str, Any] | None:
        if not self._priorities:
            return None
        if self._cycle_index >= len(self._priorities):
            self._cycle_index = 0
        return self._priorities[self._cycle_index]

    def _sync_cycle_timer(self) -> None:
        should_run = (
            self._mode == "compact"
            and not self._animating
            and not self._header_hovered
            and len(self._priorities) > 1
        )
        if should_run:
            if not self._cycle_timer.isActive():
                self._cycle_timer.start()
        elif self._cycle_timer.isActive():
            self._cycle_timer.stop()

    def _advance_priority_cycle(self) -> None:
        if self._mode != "compact" or self._animating or self._sliding:
            return
        if self._header_hovered:
            return
        if len(self._priorities) <= 1:
            self._sync_cycle_timer()
            return
        self._cycle_index = (self._cycle_index + 1) % len(self._priorities)
        shown = self._current_priority()
        self._last_priority = shown
        self._update_priority(shown, animate=True)

    def _set_stale(self, stale: bool) -> None:
        self._export_stale = stale
        if stale:
            self._fresh.setText("STALE")
            self._fresh.setStyleSheet(f"color: {HUD_WARN.name()};")
            self._fresh.setToolTip("Export is stale")
            if not self._reduce_motion and self._mode == "compact":
                if self._stale_pulse.state() != QVariantAnimation.State.Running:
                    self._stale_pulse.start()
            else:
                self._stop_stale_pulse()
        else:
            self._stop_stale_pulse()
            self._fresh.setText("LIVE")
            self._fresh.setStyleSheet(f"color: {HUD_OK.name()};")
            self._fresh.setToolTip("Export is fresh")

    def _stop_stale_pulse(self) -> None:
        if self._stale_pulse.state() == QVariantAnimation.State.Running:
            self._stale_pulse.stop()
        effect = self._fresh.graphicsEffect()
        if effect is not None:
            self._fresh.setGraphicsEffect(None)

    def _on_stale_pulse(self, value: object) -> None:
        if not self._export_stale or self._mode != "compact" or self._reduce_motion:
            return
        opacity = float(value)
        effect = self._fresh.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self._fresh)
            self._fresh.setGraphicsEffect(effect)
        effect.setOpacity(opacity)

    def _update_priority(
        self,
        priority: dict[str, Any] | None,
        *,
        animate: bool = False,
    ) -> None:
        issue_id = str(priority.get("id") or "") if priority else ""
        if not priority or not priority.get("title"):
            label = "All clear" if self._last_hud_ok else "No export"
            self._apply_priority_visual(label, None, enabled=False, tooltip=label)
            self._displayed_priority_id = None
            self._cycle_pager.setVisible(False)
            self._cycle_pager.setText("")
            return

        title = str(priority["title"])
        sev = str(priority.get("severity") or "warn")
        same = issue_id and issue_id == self._displayed_priority_id
        enabled = self._mode == "compact" and not self._animating

        if (
            animate
            and not same
            and self._mode == "compact"
            and not self._animating
            and not self._reduce_motion
        ):
            self._slide_priority(title, sev, enabled=enabled, issue_id=issue_id)
        else:
            self._apply_priority_visual(title, sev, enabled=enabled, tooltip=title)
            self._displayed_priority_id = issue_id or None

        count = len(self._priorities)
        if count > 1:
            self._cycle_pager.setVisible(True)
            self._cycle_pager.setText(f"{self._cycle_index + 1}/{count}")
            self._cycle_pager.setToolTip(f"Issue {self._cycle_index + 1} of {count}")
        else:
            self._cycle_pager.setVisible(False)
            self._cycle_pager.setText("")
            self._cycle_pager.setToolTip("")

    def _set_rail_color(self, severity: str | None) -> None:
        color = _severity_color(severity)
        self._severity_rail.setStyleSheet(
            f"QFrame#severityRail {{ background: {color.name()}; border: none; border-radius: 1px; }}"
        )
        label = _severity_label(severity)
        tip = label if label else "No active issue"
        self._severity_rail.setToolTip(tip)
        self._severity_rail.setAccessibleName(f"Severity {tip}" if tip else "Severity")

    def _apply_priority_visual(
        self,
        title: str,
        severity: str | None,
        *,
        enabled: bool,
        tooltip: str | None = None,
    ) -> None:
        self._stop_slide()
        self._layout_priority_labels()
        shown = self._elide_priority_title(title) if severity is not None else title
        active = self._prio_label_a if self._prio_active_is_a else self._prio_label_b
        idle = self._prio_label_b if self._prio_active_is_a else self._prio_label_a
        fx_active = self._prio_fx_a if self._prio_active_is_a else self._prio_fx_b
        fx_idle = self._prio_fx_b if self._prio_active_is_a else self._prio_fx_a
        active.setText(shown)
        fx_active.setOpacity(1.0)
        idle.setText("")
        fx_idle.setOpacity(0.0)
        tip = tooltip if tooltip is not None else title
        self._issue_btn.setToolTip(tip)
        active.setToolTip(tip)
        self._set_rail_color(severity)
        self._issue_btn.setEnabled(enabled)
        self._issue_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        )

    def _stop_slide(self) -> None:
        for anim in (self._slide_out, self._slide_in, self._fade_out, self._fade_in):
            if anim.state() == QPropertyAnimation.State.Running:
                anim.stop()
        self._sliding = False

    def _slide_priority(
        self,
        title: str,
        severity: str,
        *,
        enabled: bool,
        issue_id: str,
    ) -> None:
        self._stop_slide()
        self._sliding = True
        self._layout_priority_labels()
        w = max(40, self._prio_stack.width())
        h = self._prio_stack.height() or 28
        shown = self._elide_priority_title(title)

        active = self._prio_label_a if self._prio_active_is_a else self._prio_label_b
        idle = self._prio_label_b if self._prio_active_is_a else self._prio_label_a
        fx_active = self._prio_fx_a if self._prio_active_is_a else self._prio_fx_b
        fx_idle = self._prio_fx_b if self._prio_active_is_a else self._prio_fx_a

        idle.setText(shown)
        idle.setGeometry(0, 6, w, h)
        fx_idle.setOpacity(0.0)
        active.setGeometry(0, 0, w, h)
        fx_active.setOpacity(1.0)

        self._issue_btn.setToolTip(title)
        idle.setToolTip(title)
        self._set_rail_color(severity)
        self._issue_btn.setEnabled(enabled)
        self._issue_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        self._pending_slide_id = issue_id
        self._pending_slide_swap = True

        self._slide_out.setTargetObject(active)
        self._slide_in.setTargetObject(idle)
        self._fade_out.setTargetObject(fx_active)
        self._fade_in.setTargetObject(fx_idle)

        self._slide_out.setStartValue(QPoint(0, 0))
        self._slide_out.setEndValue(QPoint(0, -6))
        self._slide_in.setStartValue(QPoint(0, 6))
        self._slide_in.setEndValue(QPoint(0, 0))
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)

        self._slide_out.start()
        self._slide_in.start()
        self._fade_out.start()
        self._fade_in.start()

    def _on_slide_finished(self) -> None:
        if not self._sliding:
            return
        self._prio_active_is_a = not self._prio_active_is_a
        self._layout_priority_labels()
        idle = self._prio_label_b if self._prio_active_is_a else self._prio_label_a
        fx_idle = self._prio_fx_b if self._prio_active_is_a else self._prio_fx_a
        idle.setText("")
        fx_idle.setOpacity(0.0)
        self._displayed_priority_id = getattr(self, "_pending_slide_id", None)
        self._sliding = False

    def _on_grade_click(self) -> None:
        """Foreground the main CitiesAI window on Dashboard; keep Co-Mayor compact."""
        focus_main(self._base_url, self._token, view="dashboard")

    def _on_priority_click(self) -> None:
        if self._animating:
            # Ignore mid-expand clicks; Back/Esc still collapse.
            return
        if self._mode != "compact":
            return
        priority = self._current_priority() or self._last_priority
        if priority and priority.get("title"):
            self.expand_advisor(priority)

    def _on_input_changed(self, _text: str) -> None:
        self._send_btn.setEnabled(not self._ask_busy and bool(self._input.text().strip()))

    def _render_advisor_brief(self, priority: dict[str, Any]) -> None:
        title = html.escape(str(priority.get("title") or "Priority"))
        detail = html.escape(str(priority.get("detail") or "").strip())
        severity = str(priority.get("severity") or "info")
        sev_label = {"error": "Critical", "warn": "Warning", "info": "Info"}.get(
            severity, severity.title()
        )
        sev_color = _severity_color(severity).name()
        domain = html.escape(str(priority.get("domain") or "city").title())
        evidence = priority.get("evidence") if isinstance(priority.get("evidence"), list) else []
        causes = priority.get("likely_causes") if isinstance(priority.get("likely_causes"), list) else []
        actions = priority.get("actions") if isinstance(priority.get("actions"), list) else []
        muted = HUD_MUTED.name()
        body = HUD_BODY.name()
        ink = HUD_TEXT.name()
        sep = HUD_SEPARATOR.name()
        detail_html = (
            f'<p style="margin:4px 0 10px;color:{body};font-size:11px;line-height:1.45;">'
            f"{detail}</p>"
            if detail
            else ""
        )
        sections = [
            (
                "Evidence",
                _advisor_evidence_html(evidence),
            ),
            (
                "Likely causes",
                _advisor_list_html(causes, empty="No likely causes listed."),
            ),
            (
                "Recommended actions",
                _advisor_list_html(actions, empty="No recommended actions listed."),
            ),
        ]
        section_html = ""
        for label, content in sections:
            section_html += (
                f'<div style="margin:0 0 10px;padding:0 0 8px;'
                f'border-bottom:1px solid {sep};">'
                f'<div style="margin:0 0 4px;color:{muted};font-size:9px;'
                f'letter-spacing:0.08em;text-transform:uppercase;font-weight:600;">'
                f"{html.escape(label)}</div>{content}</div>"
            )
        self._advisor_brief.setHtml(
            f'<div style="color:{ink};">'
            f'<div style="margin:0 0 4px;">'
            f'<span style="color:{sev_color};font-family:Segoe UI,sans-serif;'
            f'font-size:10px;font-weight:700;letter-spacing:0.06em;">{html.escape(sev_label)}</span>'
            f'<span style="color:{muted};font-size:10px;"> · {domain}</span></div>'
            f'<div style="font-size:13px;font-weight:650;margin:0 0 2px;">{title}</div>'
            f"{detail_html}{section_html}</div>"
        )
        if self._mode == "advisor" and not self._animating:
            self._fit_advisor_height(animate=False)

    def _advisor_chrome_height(self) -> int:
        """Header + divider + follow-up + back buttons + margins outside the brief."""
        header_h = self._header.height() or COMPACT_PILL_HEIGHT
        follow_h = self._ask_follow_btn.sizeHint().height() or 36
        back_h = self._back_btn.sizeHint().height() or 36
        # ask_body margins (12,0,12,10) + stack spacing + divider + gaps
        return header_h + 1 + 6 + follow_h + 8 + back_h + 10 + 16

    def _max_advisor_height(self) -> int:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return max(ADVISOR_PANEL_MIN_HEIGHT, ADVISOR_PANEL_HEIGHT + 200)
        geo = screen.availableGeometry()
        # Top-anchored at y = geo.y + 12
        return max(ADVISOR_PANEL_MIN_HEIGHT, geo.height() - 12 - ADVISOR_BOTTOM_MARGIN)

    def _measure_advisor_height(self) -> int:
        """Content-sized height that grows downward; clamped to the work area."""
        chrome = self._advisor_chrome_height()
        doc = self._advisor_brief.document()
        # Use the strip content width (padding already applied by ask_body margins).
        content_width = max(120, self._strip_width - 24)
        doc.setTextWidth(content_width)
        brief_h = int(doc.size().height()) + 12
        needed = chrome + brief_h
        max_h = self._max_advisor_height()
        return max(ADVISOR_PANEL_MIN_HEIGHT, min(needed, max_h))

    def _fit_advisor_height(self, *, animate: bool) -> None:
        if self._mode != "advisor":
            return
        target = self._measure_advisor_height()
        chrome = self._advisor_chrome_height()
        brief_budget = max(80, target - chrome)
        doc_h = int(self._advisor_brief.document().size().height()) + 12
        if doc_h <= brief_budget:
            self._advisor_brief.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            self._advisor_brief.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        if abs(self.height() - target) <= 1:
            return
        if animate and not self._reduce_motion:
            self._animate_height(
                target,
                duration=EXPAND_MS,
                activate=True,
                easing=QEasingCurve.Type.OutCubic,
            )
        else:
            self._place(self._strip_width, target, activate=True)

    def expand_advisor(self, priority: dict[str, Any]) -> None:
        if self._mode in ("advisor", "ask") or self._animating:
            return
        self._cycle_timer.stop()
        self._stop_slide()
        self._last_priority = priority
        self._transcript.clear()
        self._pending_expand = priority
        self._mode = "advisor"
        self._stop_stale_pulse()
        self._update_priority(priority, animate=False)
        self._show_panel("advisor")
        self._render_advisor_brief(priority)

        self._ask_body.setVisible(True)
        self._ask_body.setMaximumHeight(16777215)
        self._thread.clear()
        self._body_opacity.setOpacity(0.0)

        target_h = self._measure_advisor_height()
        chrome = self._advisor_chrome_height()
        brief_budget = max(80, target_h - chrome)
        doc_h = int(self._advisor_brief.document().size().height()) + 12
        if doc_h <= brief_budget:
            self._advisor_brief.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            self._advisor_brief.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        def on_done() -> None:
            self._pending_expand = None
            self._fade_ask_body(to_visible=True)
            QTimer.singleShot(60, self._ask_follow_btn.setFocus)

        self._animate_height(
            target_h,
            duration=EXPAND_MS,
            activate=True,
            easing=QEasingCurve.Type.OutCubic,
            on_done=on_done,
        )

    def expand_ask(self, priority: dict[str, Any]) -> None:
        """Compatibility entry: open advisor, then enter Ask follow-up."""
        if self._mode == "ask" or self._animating:
            return
        if self._mode != "advisor":
            self.expand_advisor(priority)
        if self._mode == "advisor" and not self._animating:
            self._enter_ask_follow_up(auto_start=True)
            return

        def after_expand() -> None:
            if self._mode == "advisor" and not self._animating:
                self._enter_ask_follow_up(auto_start=True)

        QTimer.singleShot(EXPAND_MS + 40, after_expand)

    def _enter_ask_follow_up(self, *, auto_start: bool = True) -> None:
        if self._mode != "advisor" or self._animating:
            return
        priority = self._last_priority or self._current_priority() or {}
        self._mode = "ask"
        self._show_panel("ask")
        self._transcript.clear()
        self._thread.clear()
        self._input.clear()
        self._set_ask_busy(False)
        if self.height() != ASK_PANEL_HEIGHT:
            self._animate_height(
                ASK_PANEL_HEIGHT,
                duration=EXPAND_MS if not self._reduce_motion else 0,
                activate=True,
                easing=QEasingCurve.Type.OutCubic,
                on_done=lambda: QTimer.singleShot(40, self._input.setFocus),
            )
        else:
            QTimer.singleShot(40, self._input.setFocus)
        if auto_start:
            prompt = str(
                priority.get("ask_prompt")
                or f"What should I do about: {priority.get('title') or 'this issue'}?"
            )
            self._start_ask(prompt)

    def _return_to_advisor(self) -> None:
        if self._mode != "ask" or self._animating:
            return
        self._abort_ask()
        self._stop_thinking()
        self._transcript.clear()
        self._thread.clear()
        self._input.clear()
        self._set_ask_busy(False)
        self._mode = "advisor"
        self._show_panel("advisor")
        priority = self._last_priority or self._current_priority()
        if priority:
            self._render_advisor_brief(priority)
        QTimer.singleShot(40, self._ask_follow_btn.setFocus)

    def collapse_to_compact(self) -> None:
        if self._mode == "compact" and not self._animating:
            return
        self._abort_ask()
        self._stop_thinking()
        self._mode = "compact"
        self._pending_expand = None
        self._thread.clear()
        self._advisor_brief.clear()
        self._transcript.clear()
        self._input.clear()
        self._set_ask_busy(False)
        self._show_panel("advisor")
        shown = self._current_priority() or self._last_priority
        self._update_priority(shown, animate=False)
        self._fade_ask_body(to_visible=False)

        def on_done() -> None:
            self._ask_body.setVisible(False)
            self._ask_body.setMaximumHeight(0)
            self._body_opacity.setOpacity(0.0)
            self._shell_radius = SHELL_RADIUS
            self._input.clearFocus()
            self._issue_btn.clearFocus()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            self.update()
            self._place_compact(animate=False)
            if self._export_stale:
                self._set_stale(True)
            elif not self._last_hud_ok:
                self._fresh.setText("OFF")
                self._fresh.setStyleSheet(f"color: {HUD_MUTED.name()};")
            self._sync_cycle_timer()

        self._animate_height(
            COMPACT_PILL_HEIGHT,
            duration=COLLAPSE_MS,
            activate=False,
            easing=QEasingCurve.Type.InCubic,
            on_done=on_done,
        )

    def _abort_ask(self) -> None:
        if self._ask_worker is not None:
            self._ask_worker.abort()
            self._ask_worker.wait(1500)
            self._ask_worker = None
        if self._token_paint.isActive():
            self._token_paint.stop()
        self._token_dirty = False

    def _set_ask_busy(self, busy: bool) -> None:
        self._ask_busy = busy
        self._input.setEnabled(not busy)
        self._send_btn.setEnabled(not busy and bool(self._input.text().strip()))

    def _on_send(self) -> None:
        text = self._input.text().strip()
        if not text or self._ask_busy:
            return
        self._input.clear()
        self._start_ask(text)

    def _start_thinking(self) -> None:
        self._thinking = True
        self._think_step = 0
        if not self._think_timer.isActive():
            self._think_timer.start()
        self._render_thread()

    def _stop_thinking(self) -> None:
        self._thinking = False
        if self._think_timer.isActive():
            self._think_timer.stop()

    def _tick_thinking(self) -> None:
        if not self._thinking:
            self._think_timer.stop()
            return
        self._think_step = (self._think_step + 1) % 4
        self._render_thread()

    def _thinking_html(self) -> str:
        dots = "." * self._think_step
        pad = "." * (3 - self._think_step)
        sep = HUD_SEPARATOR.name()
        fg = HUD_MUTED.name()
        return (
            f'<div style="margin:6px 0;padding:0 0 0 10px;'
            f"border-left:2px solid {sep};color:{fg};"
            'font-family:Segoe UI,sans-serif;'
            'font-size:11px;letter-spacing:0.02em;line-height:1.45;">'
            f'Thinking{dots}<span style="opacity:0.3;">{pad}</span></div>'
        )

    def _render_thread(self) -> None:
        html_parts: list[str] = []
        for role, content in self._transcript:
            if role == "user":
                safe = (
                    content.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                border = _rgba(HUD_TEXT, 0.12)
                bg = _rgba(HUD_TEXT, 0.05)
                fg = HUD_TEXT.name()
                html_parts.append(
                    f'<div style="margin:4px 0 4px 14%;padding:6px 10px;border-radius:8px;'
                    f"border:1px solid {border};background:{bg};"
                    f'color:{fg};line-height:1.45;font-size:11px;">{safe}</div>'
                )
            else:
                if not content:
                    if self._thinking:
                        html_parts.append(self._thinking_html())
                    else:
                        sep = HUD_SEPARATOR.name()
                        fg = HUD_MUTED.name()
                        html_parts.append(
                            f'<div style="margin:6px 0;padding:0 0 0 10px;'
                            f"border-left:2px solid {sep};color:{fg};"
                            'font-size:11px;">...</div>'
                        )
                else:
                    body = _markdown_lite_to_html(content)
                    sep = HUD_SEPARATOR.name()
                    html_parts.append(
                        f'<div style="margin:6px 0;padding:0 0 0 10px;'
                        f"border-left:2px solid {sep};background:transparent;"
                        f'line-height:1.45;font-size:11px;">{body}</div>'
                    )
        self._thread.setHtml("".join(html_parts))
        self._thread.document().setDocumentMargin(0)
        self._thread.moveCursor(QTextCursor.MoveOperation.End)

    def _flush_token_paint(self) -> None:
        if not self._token_dirty:
            return
        self._token_dirty = False
        self._render_thread()

    def _start_ask(self, question: str) -> None:
        self._abort_ask()
        self._transcript.append(("user", question))
        self._transcript.append(("assistant", ""))
        self._start_thinking()
        self._set_ask_busy(True)

        worker = AskWorker(self._base_url, self._token, question, parent=self)
        self._ask_worker = worker

        def on_event(event: str, payload: object) -> None:
            data = payload if isinstance(payload, dict) else {}
            if event == "status":
                if self._transcript and self._transcript[-1][0] == "assistant":
                    self._transcript[-1] = ("assistant", "")
                self._start_thinking()
            elif event == "token":
                self._stop_thinking()
                text = str(data.get("text") or "")
                if self._transcript and self._transcript[-1][0] == "assistant":
                    prev = self._transcript[-1][1]
                    self._transcript[-1] = ("assistant", prev + text)
                self._token_dirty = True
                if not self._token_paint.isActive():
                    self._token_paint.start()
            elif event == "error":
                self._stop_thinking()
                if self._token_paint.isActive():
                    self._token_paint.stop()
                self._token_dirty = False
                err = str(data.get("error") or "Ask failed")
                if self._transcript and self._transcript[-1][0] == "assistant":
                    self._transcript[-1] = ("assistant", err)
                self._render_thread()
                self._set_ask_busy(False)
            elif event == "done":
                self._stop_thinking()
                if self._token_paint.isActive():
                    self._token_paint.stop()
                self._token_dirty = False
                if self._transcript and self._transcript[-1][0] == "assistant":
                    if not str(self._transcript[-1][1]).strip():
                        self._transcript[-1] = (
                            "assistant",
                            "No answer returned. Check Settings for your API key.",
                        )
                self._render_thread()
                self._set_ask_busy(False)

        worker.event_received.connect(on_event)
        worker.finished_ok.connect(lambda: self._set_ask_busy(False))
        worker.start()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._ensure_topmost()
        if self._mode == "compact" and not self._animating:
            QTimer.singleShot(0, lambda: self._place_compact(animate=False))


def run_comayor(base_url: str, token: str) -> int:
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    window = CoMayorWindow(base_url, token)
    window.show()
    return app.exec()
