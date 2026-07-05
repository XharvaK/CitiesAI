from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from citiesai.ask_core import run_ask
from citiesai.dashboard import extract_headline_metrics
from citiesai.env_store import save_env_var
from citiesai.feedback import submit_feedback
from citiesai.gui.api import api_dashboard, api_setup_preview, api_status, api_version
from citiesai.gui.server import _static_file
from citiesai.snapshot import load_snapshot, snapshot_meta
from citiesai.snapshot_history import SnapshotHistory
from citiesai.version import __version__

VENDOR_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "vendor/Cities2-DataExport/sample/latest.sample.json"
)


def test_version() -> None:
    assert __version__ == "0.4"
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__


def test_api_version() -> None:
    data = api_version()
    assert data["version"] == "0.4"


def test_collect_status_report_shape() -> None:
    report = api_status()
    assert "ok" in report
    assert "mod_installed" in report
    assert "issues" in report
    assert isinstance(report["issues"], list)
    assert "blocking_count" in report
    assert report["issue_count"] == report["blocking_count"]
    assert report["ok"] is (report["blocking_count"] == 0)


def test_extract_headline_metrics(vendor_sample: dict) -> None:
    meta = snapshot_meta(vendor_sample, path=VENDOR_SAMPLE)
    metrics = extract_headline_metrics(vendor_sample, meta)
    assert "population" in metrics
    assert metrics["city_name"] == "Evergreen Bay"


@pytest.fixture
def vendor_sample() -> dict:
    return load_snapshot(VENDOR_SAMPLE)


def test_api_dashboard_with_sample(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    export = tmp_path / "latest.json"
    export.write_text(VENDOR_SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    from citiesai import config as config_mod

    cfg = config_mod.CitiesAIConfig(export_path=export)
    monkeypatch.setattr("citiesai.gui.api.load_config", lambda: cfg)

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


def test_snapshot_history_ring() -> None:
    history = SnapshotHistory(max_points=3)
    history._points.append(  # noqa: SLF001
        type(
            "P",
            (),
            {
                "timestamp": 1.0,
                "exported_at_utc": "a",
                "metrics": {"population": 1, "employment_percent": 55},
            },
        )()
    )
    history._points.append(  # noqa: SLF001
        type(
            "P",
            (),
            {
                "timestamp": 2.0,
                "exported_at_utc": "b",
                "metrics": {"population": 3, "employment_percent": 58},
            },
        )()
    )
    data = history.to_dict()
    assert data["count"] == 2
    assert "employment_percent" in data["series"]
    assert data["series"]["employment_percent"] == [55, 58]
    assert data["deltas"]["employment_percent"] == 3


def test_save_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("citiesai.env_store._config_dir", lambda: tmp_path)
    path = save_env_var("TEST_KEY", "secret")
    assert path.is_file()
    assert "TEST_KEY" in path.read_text(encoding="utf-8")


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

    result = api_dashboard()
    assert result["ok"] is False
    assert "unreadable" in result["error"].lower()


def test_static_index_contains_title() -> None:
    body = _static_file("index.html")
    assert b"Dashboard" in body
    assert b"Issues" in body
    assert b"metric-modal" in body
    assert b"diagnostics-modal" in body
    assert b"settings-diagnostics" not in body


def test_api_setup_preview_keys() -> None:
    preview = api_setup_preview()
    assert preview["ok"] is True
    assert "export_path" in preview
