"""Headless Co-Mayor visual QA: compact/advisor/ask/stale/offline states to PNGs."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "comayor-qa"
sys.path.insert(0, str(ROOT))

from citiesai.gui import hud_window as hw  # noqa: E402


def _shot(window: hw.CoMayorWindow, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    window.grab().save(str(path))
    print(f"wrote {path} ({window.width()}x{window.height()})")


def main() -> int:
    app = QApplication(sys.argv)
    hw.prefers_reduced_motion = lambda: True  # type: ignore[assignment]

    offline = {"ok": False, "error": "missing"}
    live = {
        "ok": True,
        "meta": {"stale": False},
        "report_card": {"overall_grade": "B"},
        "fix_first": [
            {
                "id": "sewage",
                "title": "Sewage and treatment under pressure",
                "severity": "error",
                "domain": "services",
                "detail": "Fulfillment is critically low across growing districts.",
                "evidence": [
                    {"label": "Measured", "value": "Sewage fulfillment 12%"},
                    {"label": "Severity", "value": "Critical"},
                ],
                "likely_causes": [
                    "Sewage treatment capacity is below demand",
                    "Outlets or pipes are missing near growing districts",
                ],
                "actions": [
                    "Add or upgrade sewage treatment near demand",
                    "Place outlets downstream of residential growth",
                ],
                "ask_prompt": "How do I fix sewage?",
            },
            {
                "id": "power",
                "title": "Electricity shortfall",
                "severity": "error",
                "ask_prompt": "Why is power failing?",
            },
            {
                "id": "jobs",
                "title": "Unemployment is rising",
                "severity": "warn",
                "ask_prompt": "Why is unemployment rising?",
            },
        ],
        "top_priority": None,
    }
    stale = {**live, "meta": {"stale": True}}

    state = {"payload": offline}

    def fake_fetch(_url: str):
        return state["payload"]

    hw.fetch_hud = fake_fetch  # type: ignore[assignment]
    window = hw.CoMayorWindow("http://127.0.0.1:8765", "qa-token")
    window.show()

    def step_offline() -> None:
        state["payload"] = offline
        window.refresh()
        _shot(window, "01-offline")
        QTimer.singleShot(50, step_compact)

    def step_compact() -> None:
        state["payload"] = live
        window.refresh()
        _shot(window, "02-compact")
        QTimer.singleShot(50, step_stale)

    def step_stale() -> None:
        state["payload"] = stale
        window.refresh()
        _shot(window, "03-stale")
        QTimer.singleShot(50, step_advisor)

    def step_advisor() -> None:
        state["payload"] = live
        window.refresh()
        priority = window._current_priority()
        assert priority is not None
        window.expand_advisor(priority)
        _shot(window, "04-advisor")
        QTimer.singleShot(50, step_advisor_dense)

    def step_advisor_dense() -> None:
        dense = {
            "id": "power-dense",
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
        window.collapse_to_compact()
        window.expand_advisor(dense)
        _shot(window, "08-advisor-dense")
        QTimer.singleShot(50, step_ask)

    def step_ask() -> None:
        window._start_ask = lambda prompt: None  # type: ignore[method-assign]
        window._enter_ask_follow_up(auto_start=False)
        window._transcript = [
            ("user", "How do I fix sewage?"),
            (
                "assistant",
                "Place sewage outlets downstream and upgrade treatment capacity near demand.",
            ),
        ]
        window._render_thread()
        _shot(window, "05-ask")
        QTimer.singleShot(50, step_streaming)

    def step_streaming() -> None:
        window._transcript = [
            ("user", "How do I fix sewage?"),
            ("assistant", "Place sewage outlets"),
        ]
        window._thinking = True
        window._think_step = 2
        window._render_thread()
        _shot(window, "06-streaming")
        window._thinking = False
        QTimer.singleShot(50, step_collapse)

    def step_collapse() -> None:
        window.collapse_to_compact()
        _shot(window, "07-collapsed")
        QTimer.singleShot(50, app.quit)

    QTimer.singleShot(80, step_offline)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
