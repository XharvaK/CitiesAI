from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from citiesai.analyzers.report_card import build_report_card
from citiesai.analyzers.transit import analyze_transit_lines
from citiesai.diff import diff_snapshots, format_diff_markdown, resolve_snapshot_path
from citiesai.forecasts import build_forecasts
from citiesai.historian import SESSION_GAP_SECONDS, CityHistorian, _session_boundary_index
from citiesai.setup_wizard import apply_llm_provider
from citiesai.snapshot import load_snapshot, snapshot_meta

VENDOR_SAMPLE = (
    Path(__file__).resolve().parents[1]
    / "vendor/Cities2-DataExport/sample/latest.sample.json"
)


@pytest.fixture
def vendor_sample() -> dict:
    return load_snapshot(VENDOR_SAMPLE)


def test_transit_doctor_finds_line(vendor_sample: dict) -> None:
    report = analyze_transit_lines(vendor_sample)
    assert report["ok"] is True
    assert report["line_count"] >= 1
    assert report["lines"][0]["line_name"]
    assert "problem_groups" in report


def test_report_card_transit_sparse_detail_uses_mobility(vendor_sample: dict) -> None:
    snapshot = json.loads(json.dumps(vendor_sample))
    group = snapshot.setdefault("transit_line_detail_semantics", {})
    group["status"] = "ok"
    group["lines"] = group.get("lines") or [group["lines"][0]] if group.get("lines") else []
    if not group["lines"] and vendor_sample.get("transit_line_detail_semantics", {}).get("lines"):
        group["lines"] = [vendor_sample["transit_line_detail_semantics"]["lines"][0]]
    meta = snapshot_meta(snapshot, path=VENDOR_SAMPLE)
    card = build_report_card(snapshot, meta)
    transit = next(d for d in card["domains"] if d["id"] == "transit")
    assert transit["grade"] != "N/A"
    assert transit["score"] is not None


def test_report_card_transit_na_when_no_lines(vendor_sample: dict) -> None:
    snapshot = json.loads(json.dumps(vendor_sample))
    group = snapshot.setdefault("transit_line_detail_semantics", {})
    group["status"] = "ok"
    group["lines"] = []
    meta = snapshot_meta(snapshot, path=VENDOR_SAMPLE)
    card = build_report_card(snapshot, meta)
    transit = next(d for d in card["domains"] if d["id"] == "transit")
    assert transit["grade"] == "N/A"
    assert transit["score"] is None


def test_report_card_grades(vendor_sample: dict) -> None:
    meta = snapshot_meta(vendor_sample, path=VENDOR_SAMPLE)
    card = build_report_card(vendor_sample, meta)
    assert card["overall_grade"] in {"A", "B", "C", "D", "F"}
    assert len(card["domains"]) == 5
    assert "domain_scores" in card


def test_report_card_economy_surplus_projects_runway(vendor_sample: dict) -> None:
    snapshot = json.loads(json.dumps(vendor_sample))
    finance = snapshot["official_city_statistics"]["finance"]
    finance["money"] = 3_500_000
    finance["income"] = 1_580_000
    finance["expense"] = 770_000
    meta = snapshot_meta(snapshot, path=VENDOR_SAMPLE)
    card = build_report_card(snapshot, meta)
    economy = next(d for d in card["domains"] if d["id"] == "economy")
    assert economy["grade"] in {"A", "B"}
    assert economy["score"] >= 80


def test_report_card_economy_cricklade_like_surplus(vendor_sample: dict) -> None:
    snapshot = json.loads(json.dumps(vendor_sample))
    finance = snapshot["official_city_statistics"]["finance"]
    finance["money"] = 3_440_273
    finance["income"] = 1_632_775
    finance["expense"] = 772_073
    meta = snapshot_meta(snapshot, path=VENDOR_SAMPLE)
    card = build_report_card(snapshot, meta)
    economy = next(d for d in card["domains"] if d["id"] == "economy")
    assert economy["grade"] in {"A", "B"}
    assert economy["score"] >= 80


def test_report_card_economy_thin_reserves_surplus_at_least_c(vendor_sample: dict) -> None:
    snapshot = json.loads(json.dumps(vendor_sample))
    finance = snapshot["official_city_statistics"]["finance"]
    finance["money"] = 3_500_000
    finance["income"] = 1_500_000
    finance["expense"] = 1_000_000
    meta = snapshot_meta(snapshot, path=VENDOR_SAMPLE)
    card = build_report_card(snapshot, meta)
    economy = next(d for d in card["domains"] if d["id"] == "economy")
    assert economy["grade"] in {"A", "B", "C"}
    assert economy["score"] >= 70


def test_historian_metrics_schema_backfill(tmp_path: Path, vendor_sample: dict) -> None:
    export_dir = tmp_path / "CS2DataExport"
    export_dir.mkdir()
    snap_dir = export_dir / "snapshots"
    snap_dir.mkdir()
    now = datetime.now(UTC)
    old = json.loads(json.dumps(vendor_sample))
    old["exported_at_utc"] = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    new = json.loads(json.dumps(vendor_sample))
    new["exported_at_utc"] = now.isoformat().replace("+00:00", "Z")
    old_path = snap_dir / "old.json"
    latest = export_dir / "latest.json"
    old_path.write_text(json.dumps(old), encoding="utf-8")
    latest.write_text(json.dumps(new), encoding="utf-8")

    db = tmp_path / "hist.db"
    historian = CityHistorian(db_path=db)
    historian.sync(latest, force=True)
    with historian._connect() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE snapshots SET metrics_json = ?",
            (
                json.dumps(
                    {
                        "population": 1000,
                        "treasury": 100,
                    }
                ),
            ),
        )
        conn.execute(
            "UPDATE meta SET value = '1' WHERE key = 'metrics_schema_version'",
        )
        conn.commit()

    historian = CityHistorian(db_path=db)
    historian.sync(latest)
    history = historian.get_history(export_path=latest, limit=50)
    values = history["series"].get("unemployment_percent") or []
    numeric = [v for v in values if isinstance(v, (int, float))]
    assert len(numeric) >= 2


def test_diff_snapshots(vendor_sample: dict) -> None:
    modified = json.loads(json.dumps(vendor_sample))
    modified["official_city_statistics"]["finance"]["money"] = 999
    result = diff_snapshots(vendor_sample, modified)
    treasury = next(c for c in result["changes"] if c["key"] == "treasury")
    assert treasury["delta"] is not None
    md = format_diff_markdown(result)
    assert "Snapshot diff" in md


def test_resolve_snapshot_path_latest(tmp_path: Path, vendor_sample: dict) -> None:
    export_dir = tmp_path / "CS2DataExport"
    export_dir.mkdir()
    latest = export_dir / "latest.json"
    latest.write_text(json.dumps(vendor_sample), encoding="utf-8")
    assert resolve_snapshot_path("latest", export_dir=export_dir) == latest


def test_historian_ingest(tmp_path: Path, vendor_sample: dict) -> None:
    export_dir = tmp_path / "CS2DataExport"
    export_dir.mkdir()
    latest = export_dir / "latest.json"
    latest.write_text(json.dumps(vendor_sample), encoding="utf-8")
    db = tmp_path / "hist.db"
    historian = CityHistorian(db_path=db)
    sync = historian.sync(latest, force=True)
    assert sync["ingested"] >= 1
    history = historian.get_history(export_path=latest, limit=10)
    assert history["count"] >= 1


def test_historian_sync_throttle(tmp_path: Path, vendor_sample: dict) -> None:
    export_dir = tmp_path / "CS2DataExport"
    export_dir.mkdir()
    latest = export_dir / "latest.json"
    latest.write_text(json.dumps(vendor_sample), encoding="utf-8")
    historian = CityHistorian(db_path=tmp_path / "hist.db")
    first = historian.sync(latest, force=True)
    second = historian.sync(latest)
    assert first["ingested"] >= 1
    assert second.get("skipped") is True


def test_session_boundary_index() -> None:
    now = datetime.now(UTC)
    points = [
        {"exported_at_utc": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"), "metrics": {}},
        {"exported_at_utc": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"), "metrics": {}},
        {"exported_at_utc": now.isoformat().replace("+00:00", "Z"), "metrics": {}},
    ]
    assert _session_boundary_index(points, gap_seconds=SESSION_GAP_SECONDS) == 0


def test_session_digest_with_gap(tmp_path: Path, vendor_sample: dict) -> None:
    export_dir = tmp_path / "CS2DataExport"
    export_dir.mkdir()
    snap_dir = export_dir / "snapshots"
    snap_dir.mkdir()
    now = datetime.now(UTC)
    old = vendor_sample.copy()
    old_meta_time = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    old["exported_at_utc"] = old_meta_time
    new = json.loads(json.dumps(vendor_sample))
    new["exported_at_utc"] = now.isoformat().replace("+00:00", "Z")
    new["official_city_statistics"]["finance"]["money"] = 50_000_000
    (snap_dir / "old.json").write_text(json.dumps(old), encoding="utf-8")
    latest = export_dir / "latest.json"
    latest.write_text(json.dumps(new), encoding="utf-8")

    historian = CityHistorian(db_path=tmp_path / "hist.db")
    historian.sync(latest, force=True)
    hist = historian.get_history(export_path=latest, limit=500)
    digest = historian.session_digest(history=hist)
    assert digest["has_changes"] is True
    assert digest["summary"]


def test_forecasts_from_series() -> None:
    history = {
        "series": {
            "treasury": [100, 90, 80, 70, 60, 50],
            "population": [1000, 1005, 1010, 1015, 1020, 1025],
            "treasury_net_per_hour": [-1000, -1000, -1200, -1200, -1500, -2000],
        },
        "deltas": {"treasury_net_per_hour": -500},
    }
    result = build_forecasts(history)
    assert "treasury" in result["forecasts"]
    assert any("zero" in alert.lower() or "burn" in alert.lower() for alert in result["alerts"])


def test_apply_llm_provider_openai(isolated_config_dir: Path) -> None:
    from citiesai.config import load_config

    cfg = load_config()
    apply_llm_provider(cfg, "openai")
    assert cfg.llm_provider == "openai"
    assert cfg.llm_base_url == "https://api.openai.com/v1"
    assert cfg.llm_api_key_env == "OPENAI_API_KEY"
    assert cfg.llm_model == "gpt-5.5"


def test_report_scores_persisted(tmp_path: Path, vendor_sample: dict) -> None:
    export_dir = tmp_path / "CS2DataExport"
    export_dir.mkdir()
    snap_dir = export_dir / "snapshots"
    snap_dir.mkdir()
    now = datetime.now(UTC)
    old = json.loads(json.dumps(vendor_sample))
    old["exported_at_utc"] = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    new = json.loads(json.dumps(vendor_sample))
    new["exported_at_utc"] = now.isoformat().replace("+00:00", "Z")
    (snap_dir / "old.json").write_text(json.dumps(old), encoding="utf-8")
    latest = export_dir / "latest.json"
    latest.write_text(json.dumps(new), encoding="utf-8")

    historian = CityHistorian(db_path=tmp_path / "hist.db")
    historian.sync(latest, force=True)
    meta = snapshot_meta(new, path=latest)
    old_meta = snapshot_meta(old, path=snap_dir / "old.json")
    card = build_report_card(new, meta)
    city_name = card["city_name"] or "Test"
    historian.save_report_scores(
        city_name, old_meta.exported_at_utc or "old", card["domain_scores"]
    )
    historian.save_report_scores(
        city_name, meta.exported_at_utc or "t", card["domain_scores"]
    )
    hist = historian.get_history(export_path=latest, limit=500)
    assert hist["count"] >= 2
    scores = historian.previous_session_report_scores(city_name, history=hist)
    assert scores is not None
    assert "economy" in scores


def test_conversation_clears_on_city_change(isolated_config_dir: Path) -> None:
    from citiesai.conversation import ConversationStore

    store = ConversationStore(path=isolated_config_dir / "conversation.json")
    store.set_city_context("City A", "brief A")
    store.add_turn("user", "hello")
    store.set_city_context("City B", "brief B")
    assert store.messages_for_llm() == [
        {"role": "user", "content": "[Current city context]\nbrief B"},
        {"role": "assistant", "content": "Understood. I have the current city metrics."},
    ]


def test_conversation_keeps_turns_when_same_city_new_brief(isolated_config_dir: Path) -> None:
    from citiesai.conversation import ConversationStore

    store = ConversationStore(path=isolated_config_dir / "conversation.json")
    store.set_city_context("Fabius", "brief v1 population 1000")
    store.add_turn("user", "hello")
    store.set_city_context("Fabius", "brief v2 population 2000")
    messages = store.messages_for_llm()
    assert any(m.get("content") == "hello" for m in messages)
    assert messages[0]["content"].endswith("brief v2 population 2000")


def test_watch_resets_alerts_on_city_change() -> None:
    from citiesai.watch import _sync_watch_city

    state: dict = {"alerted": {"Fabius:issue:treasury": 1.0}, "active_city": "Fabius"}
    _sync_watch_city(state, "Rome")
    assert state["alerted"] == {}
    assert state["active_city"] == "Rome"


def test_mcp_initialize() -> None:
    from citiesai.mcp_server import _handle_request

    resp = _handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp is not None
    assert resp["result"]["serverInfo"]["name"] == "citiesai"


def test_mcp_unknown_tool_error() -> None:
    from citiesai.mcp_server import _handle_request

    resp = _handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "not_a_real_tool", "arguments": {}},
        }
    )
    assert resp is not None
    assert resp["result"]["isError"] is True


def test_watch_alert_cooldown() -> None:
    from citiesai.constants import WATCH_ALERT_COOLDOWN_SECONDS
    from citiesai.watch import _should_alert

    state: dict = {"alerted": {}}
    assert _should_alert(state, "issue:treasury", cooldown_seconds=WATCH_ALERT_COOLDOWN_SECONDS) is True
    assert _should_alert(state, "issue:treasury", cooldown_seconds=WATCH_ALERT_COOLDOWN_SECONDS) is False


def test_toast_xml_includes_logo() -> None:
    from citiesai.watch import build_toast_xml

    xml = build_toast_xml("Treasury critical", "Burn rate high", logo_uri="file:///C:/logo.png")
    assert 'placement="appLogoOverride"' in xml
    assert "Treasury critical" in xml
    assert "Burn rate high" in xml
    assert "ToastGeneric" in xml


def test_hidden_subprocess_kwargs_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from citiesai.watch import _hidden_subprocess_kwargs

    monkeypatch.setattr("citiesai.watch.sys.platform", "win32", raising=False)
    assert _hidden_subprocess_kwargs()["creationflags"] == subprocess.CREATE_NO_WINDOW
    monkeypatch.setattr("citiesai.watch.sys.platform", "linux", raising=False)
    assert _hidden_subprocess_kwargs() == {}


def test_analyze_budget_deficit(vendor_sample: dict) -> None:
    from citiesai.analyzers.budget import analyze_budget

    snapshot = json.loads(json.dumps(vendor_sample))
    finance = snapshot.setdefault("official_city_statistics", {}).setdefault("finance", {})
    finance["income"] = 1000
    finance["expense"] = 2500
    report = analyze_budget(snapshot)
    assert any(f["id"] == "deficit" for f in report["findings"])


def test_historian_empty_history(tmp_path: Path) -> None:
    historian = CityHistorian(db_path=tmp_path / "empty.db")
    hist = historian.get_history("Unknown City")
    assert hist["count"] == 0
    assert hist["points"] == []


def test_api_setup_save_persists(isolated_config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai import config as config_mod
    from citiesai.gui.api import api_setup_save

    export = isolated_config_dir / "latest.json"
    export.write_text("{}", encoding="utf-8")
    cfg = config_mod.CitiesAIConfig(export_path=export)
    monkeypatch.setattr("citiesai.gui.api.load_config", lambda: cfg)
    monkeypatch.setattr("citiesai.gui.api.save_detected_config", lambda **kwargs: isolated_config_dir / "config.toml")

    result = api_setup_save({"llm_provider": "openai", "llm_model": "gpt-5.5"})
    assert result["ok"] is True
    assert "config.toml" in result["config_path"]


def test_api_ask_stream_missing_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from citiesai import config as config_mod
    from citiesai.gui.api import api_ask_stream

    missing = tmp_path / "missing.json"
    cfg = config_mod.CitiesAIConfig(export_path=missing)
    monkeypatch.setattr("citiesai.gui.api.load_config", lambda: cfg)
    monkeypatch.setattr("citiesai.gui.api.load_config_cached", lambda: cfg)

    events = list(api_ask_stream({"question": "hello"}))
    assert events
    assert "error" in events[0]


def test_mcp_tools_list() -> None:
    from citiesai.mcp_server import TOOLS, _handle_request

    resp = _handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
    assert resp is not None
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {t["name"] for t in TOOLS}


def test_iter_agentic_answer_direct(monkeypatch: pytest.MonkeyPatch, vendor_sample: dict) -> None:
    from citiesai.config import CitiesAIConfig
    from citiesai.llm import iter_agentic_answer

    class FakeResponse:
        def read(self) -> bytes:
            payload = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Focus on transit first.",
                        }
                    }
                ]
            }
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(
        "citiesai.llm.resolve_llm_settings",
        lambda cfg: type("S", (), {"api_key": "x", "base_url": "http://test", "model": "m"})(),
    )
    monkeypatch.setattr("citiesai.llm._post_chat", lambda *a, **k: FakeResponse())

    cfg = CitiesAIConfig()
    events = list(
        iter_agentic_answer(
            "what next?",
            city_brief="pop 1000",
            snapshot=vendor_sample,
            cfg=cfg,
        )
    )
    assert events[0][0] == "status"
    assert any(e[0] == "result" for e in events)
    assert events[-1][1].answer == "Focus on transit first."


def test_iter_agentic_fallback_after_max_rounds(
    monkeypatch: pytest.MonkeyPatch, vendor_sample: dict
) -> None:
    from citiesai.config import CitiesAIConfig
    from citiesai.llm import iter_agentic_answer

    def fake_complete(
        messages: list[dict[str, object]],
        settings: object,
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        if tools:
            return {
                "tool_calls": [
                    {
                        "id": "t1",
                        "function": {"name": "search_wiki", "arguments": '{"query":"wellbeing"}'},
                    }
                ]
            }
        return {"content": "Pollution is lowering wellbeing."}

    monkeypatch.setattr(
        "citiesai.llm.resolve_llm_settings",
        lambda cfg: type("S", (), {"api_key": "x", "base_url": "http://test", "model": "m"})(),
    )
    monkeypatch.setattr("citiesai.llm._complete_chat", fake_complete)

    cfg = CitiesAIConfig(llm_max_tool_rounds=2)
    events = list(
        iter_agentic_answer(
            "Why did wellbeing drop?",
            city_brief="wellbeing: 62",
            snapshot=vendor_sample,
            cfg=cfg,
        )
    )
    result = events[-1][1]
    assert result.fallback_used is True
    assert "Pollution" in result.answer


def test_is_change_question() -> None:
    from citiesai.keywords import is_change_question

    assert is_change_question("Why did wellbeing drop in my city?")
    assert not is_change_question("How can I reduce round-trip times across my transit network?")


def test_build_agentic_user_content_includes_digest() -> None:
    from citiesai.ask_core import build_agentic_user_content, extract_retrieval_excerpt

    content = build_agentic_user_content(
        "Why did wellbeing drop?",
        city_brief="wellbeing: 62",
        retrieval_context="wiki: pollution lowers happiness",
        session_digest={"has_changes": True, "summary": ["Wellbeing: -8 (now 62)"]},
    )
    assert "## Recent changes (session)" in content
    assert "Wellbeing: -8" in content
    assert "## Pre-retrieved sources" in content

    bundle = "# City brief\nmetrics\n\n## Question\nwhy?\n\n---\nwiki hit"
    excerpt = extract_retrieval_excerpt(bundle)
    assert "wiki hit" in excerpt
    assert "City brief" not in excerpt


def test_config_default_max_tool_rounds() -> None:
    from citiesai.config import DEFAULT_MAX_TOOL_ROUNDS, CitiesAIConfig

    cfg = CitiesAIConfig()
    assert cfg.llm_max_tool_rounds == DEFAULT_MAX_TOOL_ROUNDS
    assert cfg.llm_agentic_enabled is True
