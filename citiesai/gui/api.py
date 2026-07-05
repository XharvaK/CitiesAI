from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..analyzers import analyze_budget, analyze_housing_labor, analyze_transit_lines
from ..ask_core import build_ask_bundle, collect_sources_for_queries, meta_to_dict, run_ask
from ..city_issues import detect_city_issues
from ..city_name import resolve_city_display_name
from ..config import config_dir, config_path, load_config, merge_discovered, set_onboarding_complete
from ..constants import HISTORY_MAX_POINTS
from ..conversation import get_conversation
from ..dashboard import extract_headline_metrics
from ..discovery import discover_paths
from ..env_store import clear_env_var, save_env_var
from ..feedback import submit_feedback
from ..forecasts import build_forecasts
from ..historian import get_historian
from ..issues import blocking_issue_count, collect_issues
from ..keywords import build_search_queries
from ..llm import (
    LLM_PRESETS,
    iter_agentic_answer,
    resolve_llm_settings,
    stream_answer,
    stream_text_chunks,
    test_api_key,
)
from ..mod_install import install_mod, mod_installed
from ..report_html import write_report_file
from ..report_ops import build_and_persist_report_card
from ..setup_wizard import save_detected_config
from ..snapshot import load_snapshot_safe, snapshot_meta
from ..status import collect_status_report
from ..suggestions import build_ask_suggestions
from ..summary import build_city_brief
from ..version import __version__
from ..watch import get_watch_service


def api_version() -> dict[str, Any]:
    return {
        "ok": True,
        "version": __version__,
        "release_url": "https://github.com/XharvaK/CitiesAI/releases",
    }


def _enriched_status() -> dict[str, Any]:
    report = collect_status_report()
    cfg = load_config()
    report["onboarding_complete"] = cfg.onboarding_complete
    report["mod_installed"] = mod_installed()
    return report


def _metrics_for_status() -> dict[str, Any] | None:
    cfg = load_config()
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return None
    snapshot, err = load_snapshot_safe(export_path)
    if snapshot is None:
        return None
    meta = snapshot_meta(snapshot, path=export_path)
    metrics = extract_headline_metrics(snapshot, meta)
    metrics["city_issues"] = detect_city_issues(snapshot)
    return metrics


def _parse_limit(raw: Any, *, default: int = 5) -> int:
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = default
    return max(1, min(limit, 10))


def _status_with_issues() -> dict[str, Any]:
    report = _enriched_status()
    metrics = _metrics_for_status()
    issues = collect_issues(report, metrics)
    blocking = blocking_issue_count(issues)
    report["issues"] = issues
    report["blocking_count"] = blocking
    report["issue_count"] = blocking
    report["ok"] = blocking == 0
    return report


def api_status() -> dict[str, Any]:
    return _status_with_issues()


def api_issues() -> dict[str, Any]:
    report = _status_with_issues()
    issues = report["issues"]
    return {
        "ok": True,
        "issues": issues,
        "count": len(issues),
        "blocking_count": report["blocking_count"],
    }


def api_suggestions() -> dict[str, Any]:
    status = _status_with_issues()
    issues = status["issues"]
    metrics = _metrics_for_status()
    llm = status.get("llm") or {}
    return {
        "ok": True,
        "suggestions": build_ask_suggestions(issues, metrics),
        "llm_configured": bool(llm.get("configured")),
    }


def api_dashboard(*, limit: int = HISTORY_MAX_POINTS) -> dict[str, Any]:
    cfg = load_config()
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return {
            "ok": False,
            "error": "No city export yet",
            "hint": "Load a city in CS2 with the Data Export mod enabled.",
        }
    snapshot, err = load_snapshot_safe(export_path)
    if snapshot is None:
        return {
            "ok": False,
            "error": "City export file is unreadable",
            "hint": "Re-load your city in CS2 or delete the corrupt latest.json and wait for a new snapshot.",
            "detail": err,
        }
    meta = snapshot_meta(snapshot, path=export_path)
    historian = get_historian()
    historian.sync(export_path)
    hist = historian.get_history(export_path=export_path, limit=limit)
    report_card = build_and_persist_report_card(snapshot, meta, historian=historian)
    forecasts = build_forecasts(hist)
    digest = historian.session_digest(history=hist)
    issues = detect_city_issues(snapshot)
    return {
        "ok": True,
        "meta": meta_to_dict(meta),
        "metrics": extract_headline_metrics(snapshot, meta),
        "historian": hist,
        "anomalies": historian.detect_anomalies(history=hist),
        "brief": build_city_brief(snapshot, meta),
        "report_card": report_card,
        "forecasts": forecasts,
        "session_digest": digest,
        "issues": issues,
    }


def api_ask(body: dict[str, Any]) -> dict[str, Any]:
    question = str(body.get("question", "")).strip()
    use_llm = bool(body.get("use_llm", True))
    limit = _parse_limit(body.get("limit", 5))
    return run_ask(question, use_llm=use_llm, limit=limit)


def api_ask_stream(body: dict[str, Any]) -> Iterator[str]:
    cfg = load_config()
    question = str(body.get("question", "")).strip()
    limit = _parse_limit(body.get("limit", 5))
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        yield _sse_event(
            "error",
            {
                "error": "No city export yet",
                "hint": "Load a city in CS2 with the Data Export mod enabled.",
            },
        )
        return
    if not question:
        yield _sse_event("error", {"error": "Question is required."})
        return

    snapshot, err = load_snapshot_safe(export_path)
    if snapshot is None:
        yield _sse_event(
            "error",
            {
                "error": "City export file is unreadable",
                "hint": "Re-load your city in CS2 or wait for a fresh snapshot.",
                "detail": err,
            },
        )
        return

    try:
        meta = snapshot_meta(snapshot, path=export_path)
        brief = build_city_brief(snapshot, meta)
        queries = build_search_queries(snapshot, question)
        sources = collect_sources_for_queries(queries, limit=limit)
        bundle = build_ask_bundle(snapshot, meta, question, limit=limit)
    except Exception as exc:  # noqa: BLE001 - surface to SSE client
        yield _sse_event("error", {"error": str(exc)})
        return

    yield _sse_event("meta", {"question": question, "meta": meta_to_dict(meta)})
    yield _sse_event("sources", {"sources": sources})
    yield _sse_event("bundle", {"bundle": bundle})

    if not bool(body.get("use_llm", True)):
        yield _sse_event("done", {"mode": "bundle"})
        return

    cfg = load_config()
    agentic = bool(body.get("agentic", True))
    try:
        if agentic:
            conv = get_conversation()
            city_name = resolve_city_display_name(snapshot, meta)
            conv.set_city_context(city_name, brief)
            result = None
            for kind, payload in iter_agentic_answer(
                question,
                city_brief=brief,
                snapshot=snapshot,
                cfg=cfg,
                history_messages=conv.messages_for_llm(),
            ):
                if kind == "status":
                    yield _sse_event("status", {"text": str(payload)})
                elif kind == "result":
                    result = payload
            if result is None:
                raise RuntimeError("Agentic loop produced no answer.")
            answer = result.answer
            conv.add_turn("user", question)
            conv.add_turn("assistant", answer, sources=sources)
            for chunk in stream_text_chunks(answer):
                yield _sse_event("token", {"text": chunk})
            yield _sse_event("done", {"mode": "llm", "agentic": True, "tool_calls": result.tool_calls})
        else:
            for chunk in stream_answer(bundle, cfg=cfg):
                yield _sse_event("token", {"text": chunk})
            yield _sse_event("done", {"mode": "llm", "agentic": False})
    except RuntimeError as exc:
        yield _sse_event("error", {"error": str(exc), "mode": "bundle", "bundle": bundle})
    except Exception as exc:  # noqa: BLE001 - surface to SSE client
        yield _sse_event("error", {"error": str(exc)})


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def api_setup_preview() -> dict[str, Any]:
    discovered = discover_paths()
    cfg = merge_discovered(load_config(), discovered)
    llm = resolve_llm_settings(cfg)
    return {
        "ok": True,
        "source": discovered.source,
        "game_dir": str(discovered.game_dir) if discovered.game_dir else None,
        "locale_cok": str(discovered.locale_cok) if discovered.locale_cok else None,
        "export_path": str(discovered.export_path),
        "llm_model": cfg.llm_model,
        "llm_provider": cfg.llm_provider,
        "llm_api_key_env": cfg.llm_api_key_env,
        "llm_configured": llm is not None,
        "config_exists": config_path().is_file(),
        "onboarding_complete": cfg.onboarding_complete,
        "mod_installed": mod_installed(),
    }


def api_setup_save(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    overrides: dict[str, Path | None] = {}
    for key in ("game_dir", "locale_cok", "export_path"):
        raw = body.get(key)
        if raw:
            overrides[key] = Path(str(raw)).expanduser()
    model = body.get("llm_model")
    provider = body.get("llm_provider")
    written = save_detected_config(
        path_overrides=overrides or None,
        llm_model=str(model) if model else None,
        llm_provider=str(provider) if provider else None,
    )
    return {"ok": True, "config_path": str(written)}


def api_onboarding_complete(_body: dict[str, Any] | None = None) -> dict[str, Any]:
    path = set_onboarding_complete(complete=True)
    return {"ok": True, "config_path": str(path)}


def api_save_key(body: dict[str, Any]) -> dict[str, Any]:
    key = str(body.get("api_key", "")).strip()
    env_name = str(body.get("env_name", "MISTRAL_API_KEY")).strip() or "MISTRAL_API_KEY"
    if not key:
        clear_env_var(env_name)
        return {"ok": True, "cleared": True}
    path = save_env_var(env_name, key)
    return {"ok": True, "env_file": str(path), "env_name": env_name}


def api_test_key() -> dict[str, Any]:
    result = test_api_key(cfg=load_config())
    return {"ok": result.get("ok", False), **result}


def api_install_mod(_body: dict[str, Any] | None = None) -> dict[str, Any]:
    return install_mod()


def api_feedback(body: dict[str, Any]) -> dict[str, Any]:
    return submit_feedback(
        category=str(body.get("category", "general")),
        message=str(body.get("message", "")),
        contact=str(body.get("contact", "")) or None,
        attach_system_info=bool(body.get("attach_system_info", False)),
        context_issue_id=str(body.get("context_issue_id", "")).strip() or None,
    )


def api_insights() -> dict[str, Any]:
    cfg = load_config()
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return {"ok": False, "error": "No city export yet"}
    snapshot, err = load_snapshot_safe(export_path)
    if snapshot is None:
        return {"ok": False, "error": err or "Unreadable export"}
    meta = snapshot_meta(snapshot, path=export_path)
    historian = get_historian()
    historian.sync(export_path)
    hist = historian.get_history(export_path=export_path, limit=HISTORY_MAX_POINTS)
    return {
        "ok": True,
        "report_card": build_and_persist_report_card(snapshot, meta, historian=historian),
        "transit": analyze_transit_lines(snapshot),
        "housing": analyze_housing_labor(snapshot),
        "budget": analyze_budget(snapshot),
        "anomalies": historian.detect_anomalies(history=hist),
    }


def api_watch_status() -> dict[str, Any]:
    service = get_watch_service()
    return {"ok": True, "enabled": service.is_running()}


def api_watch_toggle(body: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(body.get("enabled", True))
    service = get_watch_service()
    if enabled:
        service.start()
    else:
        service.stop()
    return {"ok": True, "enabled": enabled}


def api_clear_chat(_body: dict[str, Any] | None = None) -> dict[str, Any]:
    get_conversation().clear()
    return {"ok": True}


def api_export_report(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    cfg = load_config()
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return {"ok": False, "error": "No city export yet"}
    snapshot, err = load_snapshot_safe(export_path)
    if snapshot is None:
        return {"ok": False, "error": err or "Unreadable export"}
    meta = snapshot_meta(snapshot, path=export_path)
    reports_dir = (config_dir() / "reports").resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)
    raw_out = str(body.get("output", "")).strip()
    if raw_out:
        out = Path(raw_out).expanduser().resolve()
        try:
            out.relative_to(reports_dir)
        except ValueError:
            return {"ok": False, "error": f"Output must be under {reports_dir}"}
    else:
        stamp = meta.exported_at_utc.replace(":", "-") if meta.exported_at_utc else "latest"
        out = reports_dir / f"citiesai-report-{stamp}.html"
    written = write_report_file(snapshot, meta, out)
    return {"ok": True, "path": str(written)}


def api_llm_presets() -> dict[str, Any]:
    return {"ok": True, "presets": LLM_PRESETS}
