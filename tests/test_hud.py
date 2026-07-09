from __future__ import annotations

import sys
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from citiesai.gui.api import api_hud
from citiesai.gui.hud_client import _parse_sse_part, iter_sse_events
from citiesai.gui.hud_process import HudProcessController, _hud_command
from citiesai.gui.overlay import (
    COMPACT_PILL_HEIGHT,
    HUD_STATE_SIZES,
    clamp_ask_height,
    clamp_ask_width,
    clamp_compact_width,
    compact_window_size,
    dynamic_island_position,
    island_position_for_anchor,
)
from citiesai.snapshot import load_snapshot, snapshot_meta

VENDOR_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "vendor/Cities2-DataExport/sample/latest.sample.json"
)


def test_hud_state_sizes() -> None:
    compact_w, compact_h = HUD_STATE_SIZES["compact"]
    ask_w, ask_h = HUD_STATE_SIZES["ask"]
    assert compact_h == COMPACT_PILL_HEIGHT
    assert compact_w >= 180
    assert ask_w >= 360
    assert ask_h >= 320


def test_compact_width_clamp() -> None:
    assert clamp_compact_width(100) == 180
    assert clamp_compact_width(300) == 300
    assert clamp_compact_width(900) == 640


def test_ask_size_clamp() -> None:
    assert clamp_ask_width(200) == 360
    assert clamp_ask_height(200) == 320
    assert compact_window_size(280) == (280, COMPACT_PILL_HEIGHT)


def test_island_position_centered_on_anchor() -> None:
    anchor = (0, 0, 1920, 1080)
    x, y = island_position_for_anchor(anchor, 300, 44)
    assert x == 810
    assert y == 12


def test_dynamic_island_position_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("citiesai.gui.overlay._find_game_hwnd", lambda: 0)
    monkeypatch.setattr(
        "citiesai.gui.overlay._primary_monitor_work_area",
        lambda: (100, 50, 1100, 850),
    )
    x, y = dynamic_island_position(320, 44)
    assert x == 100 + (1000 - 320) // 2
    assert y == 62


def test_overlay_constants() -> None:
    from citiesai.gui.overlay import (
        ADVISOR_PANEL_HEIGHT,
        ADVISOR_PANEL_MIN_HEIGHT,
        ASK_PANEL_HEIGHT,
        ASK_PANEL_WIDTH,
        HUD_BACKGROUND_COLOR,
        SIGNAL_STRIP_WIDTH,
    )

    assert SIGNAL_STRIP_WIDTH == 460
    assert ASK_PANEL_WIDTH == SIGNAL_STRIP_WIDTH
    assert ASK_PANEL_HEIGHT == 400
    assert ADVISOR_PANEL_HEIGHT == 400
    assert ADVISOR_PANEL_MIN_HEIGHT == ADVISOR_PANEL_HEIGHT
    assert HUD_BACKGROUND_COLOR == "#0c0b09"
    assert len(HUD_BACKGROUND_COLOR) == 7
    from citiesai.gui.overlay import COMPACT_WIDTH_MAX

    assert COMPACT_WIDTH_MAX == 640


def test_prefers_reduced_motion_off_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai.gui import overlay as overlay_mod

    monkeypatch.setattr(overlay_mod.sys, "platform", "linux")
    assert overlay_mod.prefers_reduced_motion() is False


def test_close_orphan_hud_windows_noop_off_win(monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai.gui import overlay as overlay_mod

    monkeypatch.setattr(overlay_mod.sys, "platform", "linux")
    assert overlay_mod.close_orphan_hud_windows() == 0


def test_hud_process_restarts_on_token_change(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = HudProcessController()
    first = MagicMock()
    first.poll.return_value = None
    first.pid = 1001
    second = MagicMock()
    second.poll.return_value = None
    second.pid = 1002
    pops = iter([first, second])
    monkeypatch.setattr(
        "citiesai.gui.hud_process.subprocess.Popen",
        lambda *a, **k: next(pops),
    )
    monkeypatch.setattr("citiesai.gui.hud_process.close_orphan_hud_windows", lambda **k: 0)
    monkeypatch.setattr("citiesai.gui.hud_process.time.sleep", lambda *_: None)
    monkeypatch.setattr("citiesai.gui.hud_process.HUD_HEALTH_WAIT_S", 0.0)

    opened = controller.open("http://127.0.0.1:8765", "tok-a")
    assert opened["action"] == "open"
    restarted = controller.open("http://127.0.0.1:8765", "tok-b")
    assert restarted["action"] == "restart"
    assert restarted["pid"] == 1002
    first.terminate.assert_called()


def test_updates_settings_check_now_above_release_notes() -> None:
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "citiesai/gui/static/index.html").read_text(
        encoding="utf-8"
    )
    assert "settings-updates-actions" in html
    actions_idx = html.index("settings-updates-actions")
    check_now_idx = html.index('id="update-check-now"')
    notes_idx = html.index('id="update-release-notes"')
    startup_idx = html.index('id="update-check-startup"')
    assert actions_idx < check_now_idx < notes_idx
    assert startup_idx < check_now_idx
    assert "API Settings" in html
    source = Path(__file__).resolve().parents[1] / "citiesai/gui/hud_window.py"
    text = source.read_text(encoding="utf-8")
    assert "closeBtn" not in text
    assert "_close_btn" not in text
    assert "_drag_offset" not in text
    source = Path(__file__).resolve().parents[1] / "citiesai/gui/hud_window.py"
    text = source.read_text(encoding="utf-8")
    assert "closeBtn" not in text
    assert "_close_btn" not in text
    assert "_drag_offset" not in text


def test_comayor_should_be_open_requires_live_export() -> None:
    from citiesai.gui.server import comayor_should_be_open

    assert comayor_should_be_open(force_hud=False, enabled=True, live=True) is True
    assert comayor_should_be_open(force_hud=True, enabled=False, live=True) is True
    assert comayor_should_be_open(force_hud=False, enabled=True, live=False) is False
    assert comayor_should_be_open(force_hud=True, enabled=True, live=False) is False
    assert comayor_should_be_open(force_hud=False, enabled=False, live=True) is False


def test_comayor_enabled_config_roundtrip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai import config as config_mod

    monkeypatch.setattr(config_mod, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.toml")
    path = config_mod.set_comayor_enabled(enabled=False)
    assert path.is_file()
    cfg = config_mod.load_config()
    assert cfg.comayor_enabled is False
    config_mod.set_comayor_enabled(enabled=True)
    assert config_mod.load_config().comayor_enabled is True


def test_parse_sse_part_token() -> None:
    event, data = _parse_sse_part('event: token\ndata: {"text": "Hello"}')
    assert event == "token"
    assert data == {"text": "Hello"}


def test_iter_sse_events() -> None:
    chunks = [
        b'event: status\ndata: {"text": "thinking"}\n\n',
        b'event: token\ndata: {"text": "Hi"}\n\n',
        b'event: done\ndata: {"mode": "llm"}\n\n',
    ]
    events = list(iter_sse_events(iter(chunks)))
    assert events[0] == ("status", {"text": "thinking"})
    assert events[1] == ("token", {"text": "Hi"})
    assert events[2] == ("done", {"mode": "llm"})


def test_hud_command_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    cmd = _hud_command("http://127.0.0.1:8765", "tok")
    assert "-m" in cmd
    assert "citiesai.gui.hud_app" in cmd
    assert "--url=http://127.0.0.1:8765" in cmd
    assert "--token=tok" in cmd


def test_hud_command_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", r"C:\Apps\CitiesAI.exe", raising=False)
    cmd = _hud_command("http://127.0.0.1:8765", "secret")
    assert cmd[0].endswith("CitiesAI.exe")
    assert cmd[1] == "--hud-process"
    assert "--url=http://127.0.0.1:8765" in cmd
    assert "--token=secret" in cmd


def test_hud_command_leading_dash_token(monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    monkeypatch.setattr(sys, "frozen", False, raising=False)
    token = "-NTmY4dashTokenExample"
    cmd = _hud_command("http://127.0.0.1:8765", token)
    assert f"--token={token}" in cmd
    assert "--token" not in cmd  # equals-form only

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parsed = parser.parse_args(["--url=http://127.0.0.1:8765", f"--token={token}"])
    assert parsed.token == token


def test_hud_client_focus_main(monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai.gui import hud_client as hc

    captured: dict[str, object] = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true, "action": "focus", "view": "dashboard"}'

    def fake_urlopen(request, timeout=0):  # noqa: ARG001
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        return _Resp()

    monkeypatch.setattr(hc.urllib.request, "urlopen", fake_urlopen)
    result = hc.focus_main("http://127.0.0.1:8765", "tok", view="dashboard")
    assert result["ok"] is True
    assert captured["url"] == "http://127.0.0.1:8765/api/focus?view=dashboard"
    assert any("citiesai" in k.lower() or "token" in k.lower() for k in captured["headers"])


def test_hud_process_open_close(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = HudProcessController()
    fake = MagicMock()
    fake.poll.return_value = None
    fake.pid = 4242
    monkeypatch.setattr("citiesai.gui.hud_process.subprocess.Popen", lambda *a, **k: fake)
    monkeypatch.setattr("citiesai.gui.hud_process.close_orphan_hud_windows", lambda **k: 0)
    monkeypatch.setattr("citiesai.gui.hud_process.HUD_HEALTH_WAIT_S", 0.0)
    monkeypatch.setattr("citiesai.gui.hud_process.time.sleep", lambda *_: None)
    result = controller.open("http://127.0.0.1:8765", "tok")
    assert result["ok"] is True
    assert result["action"] == "open"
    assert controller.is_running() is True
    focus = controller.open("http://127.0.0.1:8765", "tok")
    assert focus["action"] == "focus"
    fake.poll.return_value = None
    controller.close()
    fake.terminate.assert_called()


def test_hud_process_reports_immediate_exit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    controller = HudProcessController()
    fake = MagicMock()
    fake.poll.return_value = 1
    fake.pid = 99
    monkeypatch.setattr("citiesai.gui.hud_process.subprocess.Popen", lambda *a, **k: fake)
    monkeypatch.setattr("citiesai.gui.hud_process.close_orphan_hud_windows", lambda **k: 0)
    monkeypatch.setattr("citiesai.gui.hud_process.HUD_HEALTH_WAIT_S", 0.2)
    monkeypatch.setattr("citiesai.gui.hud_process.config_dir", lambda: tmp_path)
    monkeypatch.setattr("citiesai.gui.hud_process.time.sleep", lambda *_: None)
    result = controller.open("http://127.0.0.1:8765", "tok")
    assert result["ok"] is False
    assert "exited immediately" in result["error"]


def test_ask_stream_surfaces_403(monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai.gui.hud_client import ask_stream

    class FakeHTTPError(urllib.error.HTTPError):
        def __init__(self) -> None:
            super().__init__(
                "http://x/api/ask/stream",
                403,
                "Forbidden",
                hdrs=None,  # type: ignore[arg-type]
                fp=None,
            )

        def read(self) -> bytes:
            return b'{"ok": false, "error": "Invalid session token"}'

    monkeypatch.setattr(
        "citiesai.gui.hud_client.urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(FakeHTTPError()),
    )
    events: list[tuple[str, dict]] = []
    ask_stream("http://127.0.0.1:8765", "stale", "hi", on_event=lambda e, p: events.append((e, p)))
    assert events
    assert events[0][0] == "error"
    assert "Invalid session token" in events[0][1]["error"]


def test_api_hud_top_priority_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    vendor_sample = load_snapshot(VENDOR_SAMPLE)
    monkeypatch.setattr(
        "citiesai.gui.api._load_live_export",
        lambda: (vendor_sample, snapshot_meta(vendor_sample, path=VENDOR_SAMPLE), VENDOR_SAMPLE),
    )
    data = api_hud()
    assert data["ok"] is True
    assert "top_priority" in data
    assert "fix_first" in data
    assert isinstance(data["fix_first"], list)
    assert len(data["fix_first"]) <= 3
    priority = data["top_priority"]
    if priority is not None:
        assert "title" in priority
        assert "severity" in priority
        assert "ask_prompt" in priority
        assert "evidence" in priority
        assert "likely_causes" in priority
        assert "actions" in priority
        assert "domain" in priority
        assert data["fix_first"]
        assert data["fix_first"][0]["id"] == priority["id"]
        assert "evidence" in data["fix_first"][0]
    for row in data["fix_first"]:
        assert "actions" in row
        assert "likely_causes" in row


def test_hud_window_module_compiles() -> None:
    import py_compile
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "citiesai/gui/hud_window.py"
    py_compile.compile(str(path), doraise=True)


def test_hud_window_signal_strip_contract() -> None:
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "citiesai/gui/hud_window.py"
    text = source.read_text(encoding="utf-8")
    assert "SIGNAL_STRIP_WIDTH" in text
    assert "CYCLE_MS = 10_000" in text
    assert "expand_advisor" in text
    assert "_enter_ask_follow_up" in text
    assert "_render_advisor_brief" in text
    assert "ADVISOR_PANEL_HEIGHT" in text
    assert "EXPAND_MS = 220" in text
    assert "COLLAPSE_MS = 180" in text
    assert "_advance_priority_cycle" in text
    assert "IssueButton" in text
    assert "severityRail" in text
    assert "signalHeader" in text
    assert "Back to game" in text
    assert "CONTENT_SWAP_AT" not in text
    assert "_swap_stack_with_fade" not in text
    assert "QParallelAnimationGroup" not in text
    assert "priorityChip" not in text
    assert "askEyebrow" not in text
    assert "_close_btn" not in text
    assert "_drag_offset" not in text


def test_hud_window_stable_width_and_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from citiesai.gui import hud_window as hw
    from citiesai.gui.overlay import (
        ADVISOR_PANEL_MIN_HEIGHT,
        ASK_PANEL_HEIGHT,
        COMPACT_PILL_HEIGHT,
        SIGNAL_STRIP_WIDTH,
    )

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(hw, "prefers_reduced_motion", lambda: True)
    monkeypatch.setattr(hw, "fetch_hud", lambda _url: {"ok": False, "error": "offline"})

    window = hw.CoMayorWindow("http://127.0.0.1:8765", "tok")
    try:
        assert window.width() == SIGNAL_STRIP_WIDTH
        assert window.height() == COMPACT_PILL_HEIGHT
        assert window._mode == "compact"
        assert window._strip_width == SIGNAL_STRIP_WIDTH

        priority = {
            "id": "city_sewage",
            "title": "Sewage and treatment under pressure",
            "severity": "error",
            "detail": "Fulfillment is critically low",
            "evidence": [{"label": "Measured", "value": "Sewage 12%"}],
            "likely_causes": ["Treatment capacity is below demand"],
            "actions": ["Add sewage treatment near demand"],
            "ask_prompt": "How do I fix sewage?",
        }
        started: list[str] = []
        monkeypatch.setattr(window, "_start_ask", lambda prompt: started.append(prompt))
        window.expand_advisor(priority)
        app.processEvents()
        assert window._mode == "advisor"
        assert window.width() == SIGNAL_STRIP_WIDTH
        assert window.height() >= ADVISOR_PANEL_MIN_HEIGHT
        assert started == []
        assert "Evidence" in window._advisor_brief.toPlainText()
        assert "Treatment capacity" in window._advisor_brief.toPlainText()

        window._enter_ask_follow_up(auto_start=True)
        app.processEvents()
        assert window._mode == "ask"
        assert window.height() == ASK_PANEL_HEIGHT
        assert started == ["How do I fix sewage?"]
        assert window._ask_body.maximumHeight() > 0
        assert not window._ask_body.isHidden()

        window.collapse_to_compact()
        app.processEvents()
        assert window._mode == "compact"
        assert window.width() == SIGNAL_STRIP_WIDTH
        assert window.height() == COMPACT_PILL_HEIGHT
        assert window._ask_body.isHidden() or window._ask_body.maximumHeight() == 0
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_hud_window_advisor_grows_for_dense_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from citiesai.gui import hud_window as hw
    from citiesai.gui.overlay import ADVISOR_PANEL_MIN_HEIGHT, SIGNAL_STRIP_WIDTH

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(hw, "prefers_reduced_motion", lambda: True)
    monkeypatch.setattr(hw, "fetch_hud", lambda _url: {"ok": False})

    window = hw.CoMayorWindow("http://127.0.0.1:8765", "tok")
    try:
        dense = {
            "id": "city_electricity",
            "title": "Electricity shortfall",
            "severity": "error",
            "domain": "services",
            "detail": (
                "Electricity pressure: shortage · fulfillment 22% · "
                "204867 wanted / 73448 capacity"
            ),
            "evidence": [
                {"label": "Measured", "value": "Electricity pressure: shortage · fulfillment 22%"},
                {"label": "Persistence", "value": "Seen across 13 recent sessions"},
                {"label": "Severity", "value": "Critical"},
                {"label": "Capacity", "value": "204867 wanted / 73448 capacity"},
            ],
            "likely_causes": [
                "Local generation and batteries are below electricity demand",
                "New growth outpaced power plant capacity",
                "Transformers are too far from demand clusters",
            ],
            "actions": [
                "Add power plants or renewable capacity",
                "Place transformers closer to demand clusters",
                "Check battery storage near industrial zones",
            ],
            "ask_prompt": "How do I fix electricity?",
        }
        window.expand_advisor(dense)
        app.processEvents()
        assert window._mode == "advisor"
        assert window.width() == SIGNAL_STRIP_WIDTH
        assert window.height() > ADVISOR_PANEL_MIN_HEIGHT
        text = window._advisor_brief.toPlainText()
        assert "Evidence" in text
        assert "Place transformers closer to demand clusters" in text
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_hud_window_grade_click_focuses_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication, QPushButton

    from citiesai.gui import hud_window as hw
    from citiesai.gui.overlay import COMPACT_PILL_HEIGHT

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(hw, "prefers_reduced_motion", lambda: True)
    monkeypatch.setattr(hw, "fetch_hud", lambda _url: {"ok": False})
    calls: list[tuple[str, str | None, str | None]] = []

    def fake_focus(base_url: str, token: str | None = None, *, view: str | None = None):
        calls.append((base_url, token, view))
        return {"ok": True, "action": "focus", "view": view}

    monkeypatch.setattr(hw, "focus_main", fake_focus)

    window = hw.CoMayorWindow("http://127.0.0.1:8765", "tok")
    try:
        assert isinstance(window._grade, QPushButton)
        window._on_grade_click()
        assert calls == [("http://127.0.0.1:8765", "tok", "dashboard")]
        assert window._mode == "compact"
        assert window.height() == COMPACT_PILL_HEIGHT
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_hud_window_cycle_preserves_current_and_pauses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from citiesai.gui import hud_window as hw

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(hw, "prefers_reduced_motion", lambda: True)
    monkeypatch.setattr(hw, "fetch_hud", lambda _url: {"ok": False})

    window = hw.CoMayorWindow("http://127.0.0.1:8765", "tok")
    try:
        items = [
            {"id": "a", "title": "Alpha issue", "severity": "warn", "ask_prompt": "A?"},
            {"id": "b", "title": "Beta issue", "severity": "error", "ask_prompt": "B?"},
            {"id": "c", "title": "Gamma issue", "severity": "info", "ask_prompt": "C?"},
        ]
        window._apply_priorities(items)
        assert window._cycle_index == 0
        assert window._cycle_timer.isActive()

        window._header_hovered = True
        window._sync_cycle_timer()
        assert not window._cycle_timer.isActive()

        window._header_hovered = False
        window._sync_cycle_timer()
        assert window._cycle_timer.isActive()

        window._cycle_index = 1
        window._apply_priorities(
            [
                {"id": "b", "title": "Beta issue", "severity": "error", "ask_prompt": "B?"},
                {"id": "c", "title": "Gamma issue", "severity": "info", "ask_prompt": "C?"},
                {"id": "a", "title": "Alpha issue", "severity": "warn", "ask_prompt": "A?"},
            ]
        )
        assert window._cycle_index == 0
        assert window._current_priority()["id"] == "b"

        window.expand_advisor(window._current_priority())
        app.processEvents()
        assert window._mode == "advisor"
        assert not window._cycle_timer.isActive()
        assert window._issue_btn.toolTip() == "Beta issue"
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_hud_window_collapse_aborts_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from citiesai.gui import hud_window as hw

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(hw, "prefers_reduced_motion", lambda: True)
    monkeypatch.setattr(hw, "fetch_hud", lambda _url: {"ok": False})

    window = hw.CoMayorWindow("http://127.0.0.1:8765", "tok")
    try:
        aborted = {"count": 0}

        class FakeWorker:
            def abort(self) -> None:
                aborted["count"] += 1

            def wait(self, _ms: int) -> None:
                return None

        priority = {
            "id": "x",
            "title": "Electricity shortfall",
            "severity": "error",
            "ask_prompt": "Why is power failing?",
        }
        monkeypatch.setattr(window, "_start_ask", lambda _prompt: None)
        window.expand_advisor(priority)
        app.processEvents()
        window._enter_ask_follow_up(auto_start=True)
        app.processEvents()
        window._ask_worker = FakeWorker()  # type: ignore[assignment]
        window.collapse_to_compact()
        app.processEvents()
        assert aborted["count"] == 1
        assert window._mode == "compact"
        assert window._ask_worker is None
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_hud_window_offline_and_stale_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtWidgets import QApplication

    from citiesai.gui import hud_window as hw

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(hw, "prefers_reduced_motion", lambda: True)

    window = hw.CoMayorWindow("http://127.0.0.1:8765", "tok")
    try:
        monkeypatch.setattr(hw, "fetch_hud", lambda _url: {"ok": False, "error": "missing"})
        window.refresh()
        active = window._prio_label_a if window._prio_active_is_a else window._prio_label_b
        assert active.text() == "No export"
        assert window._fresh.text() == "OFF"
        assert not window._issue_btn.isEnabled()

        monkeypatch.setattr(
            hw,
            "fetch_hud",
            lambda _url: {
                "ok": True,
                "meta": {"stale": True},
                "report_card": {"overall_grade": "B"},
                "fix_first": [],
                "top_priority": None,
            },
        )
        window.refresh()
        active = window._prio_label_a if window._prio_active_is_a else window._prio_label_b
        assert active.text() == "All clear"
        assert window._fresh.text() == "STALE"
        assert window._grade.text() == "B"
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_server_quit_closes_hud_before_tray() -> None:
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "citiesai/gui/server.py"
    text = source.read_text(encoding="utf-8")
    quit_idx = text.index("def quit_app")
    snippet = text[quit_idx : quit_idx + 600]
    assert "self._hud.close()" in snippet
    assert snippet.index("self._hud.close()") < snippet.index("self._tray.stop()")
    assert "start_cs2_watch" in text
    assert "is_game_running" in text
