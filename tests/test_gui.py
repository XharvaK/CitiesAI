from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from citiesai.ask_core import run_ask
from citiesai.dashboard import (
    crime_rate_percent,
    extract_headline_metrics,
    unemployment_from_workforce,
)
from citiesai.env_store import api_key_suffix, read_env_var, save_env_var
from citiesai.feedback import submit_feedback
from citiesai.gui.api import api_dashboard, api_setup_preview, api_status, api_version
from citiesai.gui.server import _static_file
from citiesai.snapshot import load_snapshot, snapshot_meta
from citiesai.version import __version__

VENDOR_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "vendor/Cities2-DataExport/sample/latest.sample.json"
)


def test_version() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__


def test_api_version() -> None:
    data = api_version()
    assert data["version"] == __version__


def test_collect_status_report_shape() -> None:
    report = api_status()
    assert "ok" in report
    assert "mod_installed" in report
    assert "issues" in report
    assert isinstance(report["issues"], list)
    assert "blocking_count" in report
    assert report["issue_count"] == report["blocking_count"]
    assert report["ok"] is (report["blocking_count"] == 0)


def test_crime_rate_percent_clamps() -> None:
    assert crime_rate_percent(104) == 100
    assert crime_rate_percent(-3) == 0
    assert crime_rate_percent(8) == 8
    assert crime_rate_percent(None) is None


def test_extract_headline_metrics_clamps_crime_rate(tmp_path: Path) -> None:
    snapshot = {
        "city": {"name": "Clampville"},
        "population": {"total_population": 1000},
        "official_city_statistics": {
            "social": {"wellbeing": 50, "health": 50, "crime_rate": 104},
            "finance": {"money": 1, "income": 1, "expense": 1},
        },
    }
    path = tmp_path / "latest.json"
    path.write_text("{}", encoding="utf-8")
    meta = snapshot_meta(snapshot, path=path)
    metrics = extract_headline_metrics(snapshot, meta)
    assert metrics["crime_rate"] == 100


def test_extract_headline_metrics(vendor_sample: dict) -> None:
    meta = snapshot_meta(vendor_sample, path=VENDOR_SAMPLE)
    metrics = extract_headline_metrics(vendor_sample, meta)
    assert "population" in metrics
    assert metrics["city_name"] == "Evergreen Bay"
    assert metrics["unemployment_percent"] == pytest.approx(5.28)
    assert metrics["congestion_percent"] == pytest.approx(4.2)
    assert metrics["crime_rate"] == 8


def test_extract_headline_metrics_utility_fulfillment() -> None:
    snapshot = {
        "city": {"building_count": 1},
        "population": {"total_population": 1000},
        "official_city_statistics": {
            "time": {"game_year": 2026, "game_month": 1},
            "finance": {"money": 1, "income": 1, "expense": 1},
            "social": {"wellbeing": 50, "health": 50, "crime_rate": 3},
        },
        "education": {"employment_rate_percent": 95},
        "utility_pressure_semantics": {
            "status": "ok",
            "water": {"fulfillment_percent": 98.0},
            "sewage": {"fulfillment_percent": 91.5},
        },
    }
    meta = snapshot_meta(snapshot, path=Path("test.json"))
    metrics = extract_headline_metrics(snapshot, meta)
    assert metrics["water_fulfillment_percent"] == pytest.approx(98.0)
    assert metrics["sewage_fulfillment_percent"] == pytest.approx(91.5)
    assert metrics["crime_rate"] == 3


def test_extract_headline_metrics_infers_utility_fulfillment() -> None:
    snapshot = {
        "city": {"building_count": 1},
        "population": {"total_population": 1000},
        "utility_pressure_semantics": {
            "status": "ok",
            "water": {"capacity": 211000, "consumption": 30706},
            "sewage": {"capacity": 100000, "consumption": 30706},
        },
    }
    meta = snapshot_meta(snapshot, path=Path("test.json"))
    metrics = extract_headline_metrics(snapshot, meta)
    assert metrics["water_fulfillment_percent"] == pytest.approx(100.0)
    assert metrics["sewage_fulfillment_percent"] == pytest.approx(100.0)


def test_extract_headline_metrics_pascal_case(vendor_sample: dict) -> None:
    snapshot = json.loads(json.dumps(vendor_sample))
    snapshot["Education"] = snapshot.pop("education")
    snapshot["TransportProxies"] = snapshot.pop("transport_proxies")
    meta = snapshot_meta(snapshot, path=VENDOR_SAMPLE)
    metrics = extract_headline_metrics(snapshot, meta)
    assert metrics["unemployment_percent"] == pytest.approx(5.28)
    assert metrics["congestion_percent"] == pytest.approx(4.2)


def test_unemployment_workforce_fallback() -> None:
    workforce = {"Workers": 2774, "Unemployed": 1491}
    assert unemployment_from_workforce(workforce) == pytest.approx(34.96, abs=0.01)


def test_unemployment_workforce_fallback_in_metrics(vendor_sample: dict) -> None:
    snapshot = json.loads(json.dumps(vendor_sample))
    snapshot["education"]["employment_rate_percent"] = None
    snapshot["workforce"]["workers"] = 80
    snapshot["workforce"]["unemployed"] = 20
    meta = snapshot_meta(snapshot, path=VENDOR_SAMPLE)
    metrics = extract_headline_metrics(snapshot, meta)
    assert metrics["unemployment_percent"] == pytest.approx(20.0)


@pytest.fixture
def vendor_sample() -> dict:
    return load_snapshot(VENDOR_SAMPLE)


def test_api_dashboard_with_sample(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    export = tmp_path / "latest.json"
    export.write_text(VENDOR_SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    from citiesai import config as config_mod

    cfg = config_mod.CitiesAIConfig(export_path=export)
    monkeypatch.setattr("citiesai.gui.api.load_config", lambda: cfg)
    monkeypatch.setattr("citiesai.gui.api.load_config_cached", lambda: cfg)

    result = api_dashboard()
    assert result["ok"] is True
    assert result["metrics"]["city_name"] == "Evergreen Bay"


def test_run_ask_no_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai import config as config_mod

    missing = tmp_path / "missing.json"
    cfg = config_mod.CitiesAIConfig(export_path=missing)
    monkeypatch.setattr("citiesai.ask_core.load_config", lambda: cfg)

    result = run_ask("hello", use_llm=False)
    assert result["ok"] is False


def test_run_ask_respects_agentic_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from citiesai import config as config_mod

    export = tmp_path / "latest.json"
    export.write_text(VENDOR_SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    cfg = config_mod.CitiesAIConfig(export_path=export, llm_agentic_enabled=False)
    monkeypatch.setattr("citiesai.ask_core.load_config", lambda: cfg)

    called: list[str] = []

    def _fake_generate(*_a, **_k):
        called.append("single")
        return "single-shot answer"

    def _fake_agentic(*_a, **_k):
        called.append("agentic")
        raise AssertionError("agentic path should not run when Deep research is off")

    monkeypatch.setattr("citiesai.ask_core.generate_answer", _fake_generate)
    monkeypatch.setattr("citiesai.ask_core.generate_agentic_answer", _fake_agentic)

    result = run_ask("Why is my budget negative?", use_llm=True, agentic=None)
    assert result["ok"] is True
    assert result["agentic"] is False
    assert called == ["single"]

def test_save_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("citiesai.env_store._config_dir", lambda: tmp_path)
    path = save_env_var("TEST_KEY", "secret")
    assert path.is_file()
    assert "TEST_KEY" in path.read_text(encoding="utf-8")


def test_read_env_var_reads_saved_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("citiesai.env_store._config_dir", lambda: tmp_path)
    monkeypatch.delenv("TEST_KEY", raising=False)
    save_env_var("TEST_KEY", "sk-test-secret9abc")
    monkeypatch.delenv("TEST_KEY", raising=False)
    assert read_env_var("TEST_KEY") == "sk-test-secret9abc"


def test_api_key_suffix_masks_key() -> None:
    assert api_key_suffix("sk-test-secret9abc") == "9abc"
    assert api_key_suffix("local") is None
    assert api_key_suffix("abc") is None


def test_api_setup_preview_includes_api_key_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai.llm import LLMSettings

    monkeypatch.setattr(
        "citiesai.gui.api.read_env_var",
        lambda _name: "sk-test-secret9abc",
    )
    monkeypatch.setattr(
        "citiesai.gui.api.resolve_llm_settings",
        lambda _cfg: LLMSettings(
            base_url="https://api.mistral.ai/v1",
            model="mistral-medium-latest",
            api_key="sk-test-secret9abc",
            api_key_env="MISTRAL_API_KEY",
        ),
    )
    result = api_setup_preview()
    assert result["llm_configured"] is True
    assert result["api_key_suffix"] == "9abc"


def test_api_install_mod_accepts_post_body() -> None:
    from citiesai.gui.api import api_install_mod

    result = api_install_mod({})
    assert "ok" in result


def test_feedback_local_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("citiesai.feedback.config_dir", lambda: tmp_path)
    monkeypatch.setattr("citiesai.feedback._discord_webhook_url", lambda: None)
    result = submit_feedback(category="bug", message="test message", attach_system_info=False)
    assert result["ok"] is True
    assert result["mode"] == "local"


def test_read_webhook_file_strips_utf8_bom(tmp_path: Path) -> None:
    from citiesai.feedback import _read_webhook_file

    path = tmp_path / "feedback_webhook.url"
    path.write_bytes(
        bytes([0xEF, 0xBB, 0xBF])
        + b"https://discord.com/api/webhooks/1234567890/test-token"
    )
    assert (
        _read_webhook_file(path)
        == "https://discord.com/api/webhooks/1234567890/test-token"
    )


def test_load_config_migrates_legacy_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai import config as config_mod

    config_dir = tmp_path / "CitiesAI"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    config_file.write_text(
        '[llm]\nprovider = "mistral"\nmodel = "mistral-small-latest"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config_mod, "config_path", lambda: config_file)

    cfg = config_mod.load_config()
    assert cfg.llm_model == config_mod.DEFAULT_LLM_MODEL
    assert config_mod.DEFAULT_LLM_MODEL in config_file.read_text(encoding="utf-8")


def test_api_dashboard_corrupt_export(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    export = tmp_path / "latest.json"
    export.write_text("{not valid json", encoding="utf-8")

    from citiesai import config as config_mod

    cfg = config_mod.CitiesAIConfig(export_path=export)
    monkeypatch.setattr("citiesai.gui.api.load_config", lambda: cfg)
    monkeypatch.setattr("citiesai.gui.api.load_config_cached", lambda: cfg)

    result = api_dashboard()
    assert result["ok"] is False
    assert "unreadable" in result["error"].lower()


def test_static_index_contains_title() -> None:
    body = _static_file("index.html")
    css = _static_file("app.css")
    js = _static_file("app.js")
    assert b"Dashboard" in body
    assert b"Issues" in body
    assert b"Advisor" in body
    assert b'id="metric-modal"' in body
    assert b'role="dialog"' in body
    assert b"metric-modal-backdrop" in body
    assert b"diagnostics-modal" in body
    assert b"api-key-saved" in body
    assert b"nav-group" not in body
    assert b"priority-hero" not in body
    assert b"metric-ledger" not in body
    assert b'class="metric-grid"' in body
    assert b"issue-inspector" in body
    assert b"inspector-ask-composer" in body
    assert b"advisor-style" in body
    assert b"watch-enabled" in body
    assert b"settings-section-advanced" in body
    assert b"nav-icon-btn" in body
    assert b"sidebar-foot-icons" in body
    assert b'aria-label="Settings"' in body
    # Cogwheel path (not the old sunburst radial ticks).
    assert b"M19.4 15a1.65 1.65 0 0 0 .33 1.82" in body
    assert b"M12 2v2.2M12 19.8V22" not in body
    assert b"insights-index" not in body
    assert b"IBM Plex" not in css
    assert b'"Segoe UI"' in css
    assert b"side-inspector" in css
    assert b"var(--mono)" not in css
    assert b"justify-content: center" in css
    assert b"metric-inspector-overlay" not in css
    assert b"metric-signal" in css
    assert b"report-grade-cluster" in css
    assert b"grade-badge-lg" in css
    assert b"metric-signal" in js
    assert b"report-grade-cluster" in js
    assert b"bindModalFocusTrap(inspector, closeMetricModal)" in js
    assert b"API Settings" in body
    assert b"settings-updates-actions" in body
    assert b"preserveSelection: preserve" in js
    assert b"preserveSelection = true" in js
    assert b"stabilizeIssueOrder" in js
    assert b"softRefreshIssueInspector" in js
    assert b'key: "health"' in js
    assert b'key: "wellbeing"' in js
    # Health/wellbeing cards show % like other rate metrics.
    assert js.count(b'suffix: "%"') >= 6
    # Follow-up composer: one shell border, not a nested textarea border.
    assert b".inspector-ask-composer #issue-ask-input" in css
    assert b"border: none" in css
    # Issues Send redirects to Advisor (same path as Insights), not inline SSE.
    assert b"askIssueFollowUp" not in js
    assert b'askFromPrompt($("issue-ask-input")' in js
    assert b"issue-ask-log" not in body
    assert b".inspector-ask-composer" in css
    assert b"align-items: stretch" in css
    assert b".inspector-ask-composer #issue-ask-submit" in css
    # Sidebar brand keeps mixed-case CitiesAI (not CSS uppercase on .brand-title).
    assert b'class="brand-title">CitiesAI</div>' in body
    for chunk in css.split(b".brand-title {"):
        block = chunk.split(b"}", 1)[0]
        assert b"text-transform: uppercase" not in block


def test_api_focus_bare_and_view(monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai.gui import api as api_mod

    calls: list[dict[str, str | None]] = []

    def handler(*, view: str | None = None) -> None:
        calls.append({"view": view})

    api_mod.register_focus_handler(handler)
    try:
        bare = api_mod.api_focus()
        assert bare["ok"] is True
        assert bare["action"] == "focus"
        assert bare.get("view") is None
        assert calls[-1]["view"] is None

        dash = api_mod.api_focus(view="dashboard")
        assert dash["ok"] is True
        assert dash["view"] == "dashboard"
        assert calls[-1]["view"] == "dashboard"

        bad = api_mod.api_focus(view="not-a-view")
        assert bad["ok"] is False
        assert "Unsupported" in bad["error"]
    finally:
        api_mod.register_focus_handler(lambda: None)


def test_api_setup_preview_keys() -> None:
    preview = api_setup_preview()
    assert preview["ok"] is True
    assert "export_path" in preview
