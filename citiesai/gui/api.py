from __future__ import annotations

import json
import urllib.error
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from ..analyzers import (
    analyze_access_gaps,
    analyze_budget,
    analyze_demand_factors,
    analyze_housing_labor,
    analyze_transit_lines,
    analyze_utilities_services,
    build_report_card,
)
from ..ask_core import (
    build_ask_bundle_and_sources,
    classify_ask_intent,
    meta_to_dict,
    needs_knowledge_retrieval,
    prepare_agentic_ask,
)
from ..briefing import build_mayors_briefing
from ..cache import load_config_cached, load_export_cached
from ..city_issues import detect_city_issues
from ..city_name import resolve_city_display_name
from ..config import (
    config_dir,
    config_path,
    load_config,
    merge_discovered,
    normalize_advisor_style,
    set_advisor_style,
    set_comayor_enabled,
    set_onboarding_complete,
    set_watch_enabled,
)
from ..constants import HISTORY_MAX_POINTS, STALE_AFTER_SECONDS
from ..conversation import get_conversation
from ..dashboard import extract_headline_metrics
from ..discovery import discover_paths
from ..env_store import api_key_suffix, clear_env_var, read_env_var, save_env_var
from ..feedback import submit_feedback
from ..forecasts import build_forecasts
from ..historian import get_historian
from ..issue_advisor import enrich_issue_advisor, enrich_issues, rank_issues_for_queue
from ..issues import blocking_issue_count, collect_issues
from ..llm import (
    LLM_PRESETS,
    iter_agentic_answer,
    resolve_llm_settings,
    stream_answer,
    stream_text_chunks,
    test_api_key,
)
from ..mod_install import install_mod, mod_installed
from ..official_fallbacks import fill_official_metric_gaps
from ..report_html import write_report_file
from ..report_ops import build_and_persist_report_card
from ..setup_wizard import apply_llm_provider, save_detected_config
from ..snapshot import snapshot_meta
from ..status import collect_status_report
from ..suggestions import build_ask_suggestions
from ..summary import build_city_brief
from ..updater import (
    check_for_update,
    clear_update_cache,
    dismiss_update,
    download_installer,
    launch_installer,
    save_update_settings,
)
from ..version import __version__
from ..watch import get_watch_service


def _load_live_export() -> tuple[dict[str, Any], Any, Path]:
    cfg = load_config_cached()
    export_path = cfg.resolved_export_path()
    snapshot, err = load_export_cached(export_path)
    if snapshot is None:
        raise RuntimeError(err or f"Export not found: {export_path}")
    meta = snapshot_meta(snapshot, path=export_path)
    return snapshot, meta, export_path


def _top_city_priorities(issues: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    city = [issue for issue in issues if issue.get("kind") == "city"]
    return enrich_issues(rank_issues_for_queue(city))[:limit]


def api_hud() -> dict[str, Any]:
    global _hud_cache
    try:
        snapshot, meta, export_path = _load_live_export()
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    cfg = load_config_cached()
    mtime = _export_mtime(export_path)
    cache_key = (str(export_path.resolve()), mtime, cfg.advisor_style)
    if (
        _hud_cache
        and _hud_cache.get("key") == cache_key
        and _hud_cache.get("payload", {}).get("ok")
    ):
        return _refresh_meta_age(_hud_cache["payload"], meta)

    historian = get_historian()
    history = historian.get_history(export_path=meta.path)
    report_card = build_report_card(
        snapshot,
        meta,
        previous_domain_scores=historian.previous_session_report_scores(
            str(history.get("city_name") or ""),
            history=history,
        ),
    )
    issues = detect_city_issues(snapshot)
    issues = historian.enrich_issues_with_lifecycle(issues, city_name=history.get("city_name"))
    priorities = _top_city_priorities(issues)
    top_priority = priorities[0] if priorities else None
    age_seconds = meta.age_seconds if meta.age_seconds is not None else 0
    stale = age_seconds > STALE_AFTER_SECONDS
    payload = {
        "ok": True,
        "meta": {
            **meta_to_dict(meta),
            "age_seconds": age_seconds,
            "stale": stale,
        },
        "report_card": {
            "overall_grade": report_card.get("overall_grade"),
            "overall_score": report_card.get("overall_score"),
        },
        "top_priority": enrich_issue_advisor(top_priority) if top_priority else None,
        "priorities": priorities,
        "advisor_style": cfg.advisor_style,
    }
    _hud_cache = {"key": cache_key, "payload": payload}
    return payload


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
    cfg = load_config_cached()
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return None
    snapshot, err = load_export_cached(export_path)
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
    report["metrics"] = metrics
    report["blocking_count"] = blocking
    report["issue_count"] = blocking
    report["ok"] = blocking == 0
    return report


def api_status() -> dict[str, Any]:
    return _status_with_issues()


def _sync_city_state(
    snapshot: dict[str, Any],
    meta: Any,
    issues: list[dict[str, Any]],
    *,
    historian: Any | None = None,
    skip_sync: bool = False,
) -> str:
    city_name = resolve_city_display_name(snapshot, meta)
    hist = historian or get_historian()
    if not skip_sync:
        hist.sync(meta.path)
    hist.sync_tracked_issues(city_name, issues)
    return city_name


def _append_anomaly_issues(
    issues: list[dict[str, Any]],
    *,
    city_name: str,
    export_path: Path,
    historian: Any | None = None,
    history: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    hist = historian or get_historian()
    existing = {str(issue.get("id")) for issue in issues}
    merged = list(issues)
    for row in hist.detect_anomalies(city_name, export_path=export_path, history=history):
        issue_id = str(row.get("id") or "")
        if not issue_id or issue_id in existing:
            continue
        merged.append(
            {
                "id": issue_id,
                "kind": "city",
                "severity": row.get("severity", "info"),
                "title": row.get("title", "Anomaly"),
                "detail": row.get("detail", ""),
                "ask_prompt": row.get("ask_prompt", ""),
                "report_category": "anomaly",
            }
        )
        existing.add(issue_id)
    return merged


def api_issues() -> dict[str, Any]:
    report = _status_with_issues()
    issues = report["issues"]
    city_name = None
    cfg = load_config_cached()
    export_path = cfg.resolved_export_path()
    if export_path.is_file():
        snapshot, err = load_export_cached(export_path)
        if snapshot is not None:
            meta = snapshot_meta(snapshot, path=export_path)
            city_name = _sync_city_state(snapshot, meta, issues)
            historian = get_historian()
            issues = _append_anomaly_issues(
                issues,
                city_name=city_name,
                export_path=export_path,
                historian=historian,
            )
            issues = historian.enrich_issues_with_lifecycle(issues, city_name=city_name)
    ranked = rank_issues_for_queue(enrich_issues(issues))
    return {
        "ok": True,
        "issues": ranked,
        "count": len(ranked),
        "blocking_count": report["blocking_count"],
    }


def api_suggestions() -> dict[str, Any]:
    status = _status_with_issues()
    issues = status["issues"]
    metrics = status.get("metrics")
    if metrics is None:
        metrics = _metrics_for_status()
    llm = status.get("llm") or {}
    cfg = load_config_cached()
    return {
        "ok": True,
        "suggestions": build_ask_suggestions(
            issues,
            metrics,
            advisor_style=cfg.advisor_style,
        ),
        "llm_configured": bool(llm.get("configured")),
        "advisor_style": cfg.advisor_style,
    }


_dashboard_cache: dict[str, Any] | None = None
_hud_cache: dict[str, Any] | None = None


def _export_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime if path.is_file() else 0.0
    except OSError:
        return 0.0


def _refresh_meta_age(payload: dict[str, Any], meta: Any) -> dict[str, Any]:
    meta_dict = dict(payload.get("meta") or {})
    meta_dict.update(meta_to_dict(meta))
    payload = {**payload, "meta": meta_dict}
    return payload


def api_dashboard(*, limit: int = HISTORY_MAX_POINTS) -> dict[str, Any]:
    global _dashboard_cache
    cfg = load_config_cached()
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return {
            "ok": False,
            "error": "No city export yet",
            "hint": "Load a city in CS2 with the Data Export mod enabled.",
        }
    mtime = _export_mtime(export_path)
    cache_key = (str(export_path.resolve()), mtime, limit, cfg.advisor_style)
    if (
        _dashboard_cache
        and _dashboard_cache.get("key") == cache_key
        and _dashboard_cache.get("payload", {}).get("ok")
    ):
        snapshot, _err = load_export_cached(export_path)
        if snapshot is not None:
            meta = snapshot_meta(snapshot, path=export_path)
            return _refresh_meta_age(_dashboard_cache["payload"], meta)

    snapshot, err = load_export_cached(export_path)
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
    issues = detect_city_issues(snapshot)
    city_name = _sync_city_state(
        snapshot,
        meta,
        issues,
        historian=historian,
        skip_sync=True,
    )
    issues = _append_anomaly_issues(
        issues,
        city_name=city_name,
        export_path=export_path,
        historian=historian,
        history=hist,
    )
    issues = historian.enrich_issues_with_lifecycle(issues, city_name=city_name)
    metrics = fill_official_metric_gaps(
        extract_headline_metrics(snapshot, meta),
        hist,
        snapshot=snapshot,
    )
    report_card = build_and_persist_report_card(
        snapshot,
        meta,
        historian=historian,
        headline_metrics=metrics,
        history=hist,
    )
    forecasts = build_forecasts(hist)
    priorities = _top_city_priorities(issues)
    payload = {
        "ok": True,
        "meta": meta_to_dict(meta),
        "metrics": metrics,
        "historian": hist,
        "brief": build_city_brief(snapshot, meta),
        "report_card": report_card,
        "forecasts": forecasts,
        "priorities": priorities,
        "issues": enrich_issues(rank_issues_for_queue(issues)),
        "advisor_style": cfg.advisor_style,
    }
    _dashboard_cache = {"key": cache_key, "payload": payload}
    return payload


def api_ask_stream(body: dict[str, Any]) -> Iterator[str]:
    cfg = load_config_cached()
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

    if bool(body.get("use_llm", True)) and resolve_llm_settings(cfg) is None:
        yield _sse_event(
            "error",
            {
                "error": "No LLM API key found",
                "hint": "Add a free Mistral (or OpenAI) key in Settings → AI answers. "
                "Dashboard, Insights, and Issues work without a key.",
            },
        )
        return

    snapshot, err = load_export_cached(export_path)
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

    intent = classify_ask_intent(question)
    retrieve = needs_knowledge_retrieval(intent)
    try:
        meta = snapshot_meta(snapshot, path=export_path)
        brief = build_city_brief(snapshot, meta)
        bundle, sources = build_ask_bundle_and_sources(
            snapshot,
            meta,
            question,
            limit=limit,
            retrieve=retrieve,
            brief=brief,
        )
    except Exception as exc:  # noqa: BLE001 - surface to SSE client
        yield _sse_event("error", {"error": str(exc)})
        return

    yield _sse_event(
        "meta",
        {"question": question, "meta": meta_to_dict(meta), "intent": intent},
    )
    yield _sse_event("sources", {"sources": sources})
    yield _sse_event("bundle", {"bundle": bundle})

    if not bool(body.get("use_llm", True)):
        yield _sse_event("done", {"mode": "bundle"})
        return

    if "agentic" in body:
        agentic = bool(body.get("agentic"))
    else:
        agentic = cfg.llm_agentic_enabled
    # Non-gameplay routes stay single-shot (prompt already covers app/setup/classification).
    agentic = bool(agentic and intent == "gameplay")
    try:
        if agentic:
            conv = get_conversation()
            city_name = resolve_city_display_name(snapshot, meta)
            conv.set_city_context(city_name, brief)
            user_content, retrieval_context, retrieval_bundle = prepare_agentic_ask(
                question,
                brief=brief,
                bundle=bundle,
                export_path=export_path,
            )
            result = None
            answer = ""
            streamed_tokens = False
            for kind, payload in iter_agentic_answer(
                question,
                city_brief=brief,
                snapshot=snapshot,
                cfg=cfg,
                history_messages=conv.messages_for_llm(),
                retrieval_context=retrieval_context,
                retrieval_bundle=retrieval_bundle,
                user_content=user_content,
            ):
                if kind == "status":
                    yield _sse_event("status", {"text": str(payload)})
                elif kind == "token":
                    streamed_tokens = True
                    answer += str(payload)
                    yield _sse_event("token", {"text": str(payload)})
                elif kind == "result":
                    result = payload
            if result is None:
                raise RuntimeError("Agentic loop produced no answer.")
            if not answer:
                answer = result.answer
            if not streamed_tokens:
                for chunk in stream_text_chunks(answer):
                    yield _sse_event("token", {"text": chunk})
            tool_sources = [
                {"source": "tool", "title": name, "snippet": ""} for name in result.tool_calls
            ]
            all_sources = sources + tool_sources
            yield _sse_event("sources", {"sources": all_sources})
            conv.add_turn("user", question)
            conv.add_turn("assistant", answer, sources=all_sources)
            yield _sse_event(
                "done",
                {
                    "mode": "llm",
                    "agentic": True,
                    "tool_calls": result.tool_calls,
                    "fallback_used": result.fallback_used,
                },
            )
        else:
            conv = get_conversation()
            city_name = resolve_city_display_name(snapshot, meta)
            conv.set_city_context(city_name, brief)
            answer = ""
            for chunk in stream_answer(bundle, cfg=cfg, history_messages=conv.messages_for_llm()):
                answer += chunk
                yield _sse_event("token", {"text": chunk})
            conv.add_turn("user", question)
            conv.add_turn("assistant", answer, sources=sources)
            yield _sse_event("done", {"mode": "llm", "agentic": False})
    except RuntimeError as exc:
        yield _sse_event("error", {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - surface to SSE client
        yield _sse_event("error", {"error": str(exc)})


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def api_setup_preview() -> dict[str, Any]:
    discovered = discover_paths()
    cfg = merge_discovered(load_config(), discovered)
    llm = resolve_llm_settings(cfg)
    stored_key = read_env_var(cfg.llm_api_key_env)
    suffix = api_key_suffix(stored_key)
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
        "api_key_suffix": suffix,
        "llm_agentic_enabled": cfg.llm_agentic_enabled,
        "llm_max_tool_rounds": cfg.llm_max_tool_rounds,
        "config_exists": config_path().is_file(),
        "onboarding_complete": cfg.onboarding_complete,
        "comayor_enabled": cfg.comayor_enabled,
        "advisor_style": normalize_advisor_style(cfg.advisor_style),
        "watch_enabled": bool(cfg.watch_enabled),
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
    agentic = body.get("llm_agentic_enabled")
    advisor_style = body.get("advisor_style")
    written = save_detected_config(
        path_overrides=overrides or None,
        llm_model=str(model) if model else None,
        llm_provider=str(provider) if provider else None,
        llm_agentic_enabled=bool(agentic) if agentic is not None else None,
        advisor_style=str(advisor_style) if advisor_style is not None else None,
    )
    return {"ok": True, "config_path": str(written)}


def api_onboarding_complete(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    if body.get("advisor_style") is not None:
        set_advisor_style(str(body.get("advisor_style")))
    path = set_onboarding_complete(complete=True)
    return {"ok": True, "config_path": str(path)}


def api_save_key(body: dict[str, Any]) -> dict[str, Any]:
    key = str(body.get("api_key", "")).strip()
    env_name = str(body.get("env_name", "")).strip()
    if not env_name:
        provider = str(body.get("llm_provider", "")).strip()
        preset = LLM_PRESETS.get(provider)
        env_name = preset["api_key_env"] if preset else "MISTRAL_API_KEY"
    if not key:
        clear_env_var(env_name)
        return {"ok": True, "cleared": True}
    path = save_env_var(env_name, key)
    return {"ok": True, "env_file": str(path), "env_name": env_name}


def api_test_key(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    cfg = load_config()
    provider = body.get("llm_provider")
    model = body.get("llm_model")
    if provider:
        apply_llm_provider(cfg, str(provider))
    if model:
        cfg.llm_model = str(model)
    result = test_api_key(cfg=cfg)
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


def api_feedback_answer(body: dict[str, Any]) -> dict[str, Any]:
    rating = str(body.get("rating", "")).strip().lower()
    if rating not in {"up", "down"}:
        return {"ok": False, "error": "rating must be 'up' or 'down'"}
    question = str(body.get("question", "")).strip()
    answer = str(body.get("answer", "")).strip()
    if not question or not answer:
        return {"ok": False, "error": "question and answer are required"}
    category = "wrong-answer" if rating == "down" else "general"
    prefix = "Helpful answer" if rating == "up" else "Unhelpful answer"
    message = (
        f"{prefix}\n\nQ: {question[:500]}\n\nA: {answer[:2000]}"
    )
    return submit_feedback(category=category, message=message, attach_system_info=True)


def api_briefing() -> dict[str, Any]:
    cfg = load_config_cached()
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return {"ok": False, "error": "No city export yet"}
    snapshot, err = load_export_cached(export_path)
    if snapshot is None:
        return {"ok": False, "error": err or "Unreadable export"}
    meta = snapshot_meta(snapshot, path=export_path)
    historian = get_historian()
    historian.sync(export_path)
    history = historian.get_history(export_path=export_path)
    issues = detect_city_issues(snapshot)
    city_name = _sync_city_state(snapshot, meta, issues)
    issues = historian.enrich_issues_with_lifecycle(issues, city_name=city_name)
    report_card = build_report_card(
        snapshot,
        meta,
        previous_domain_scores=historian.previous_session_report_scores(
            str(history.get("city_name") or ""),
            history=history,
        ),
    )
    forecasts = build_forecasts(history)
    digest = historian.session_digest(history=history)
    briefing = build_mayors_briefing(
        snapshot,
        meta,
        historian=historian,
        history=history,
        issues=issues,
        report_card=report_card,
        forecasts=forecasts,
        digest=digest,
    )
    return {"ok": True, "briefing": briefing}


def api_insights() -> dict[str, Any]:
    cfg = load_config_cached()
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return {"ok": False, "error": "No city export yet"}
    snapshot, err = load_export_cached(export_path)
    if snapshot is None:
        return {"ok": False, "error": err or "Unreadable export"}
    meta = snapshot_meta(snapshot, path=export_path)
    historian = get_historian()
    historian.sync(export_path)
    city_name = resolve_city_display_name(snapshot, meta)
    return {
        "ok": True,
        "meta": meta_to_dict(meta),
        "report_card": build_and_persist_report_card(snapshot, meta, historian=historian),
        "transit": analyze_transit_lines(snapshot),
        "access_gaps": analyze_access_gaps(snapshot),
        "demand_factors": analyze_demand_factors(snapshot),
        "utilities_services": analyze_utilities_services(snapshot),
        "housing": analyze_housing_labor(snapshot),
        "budget": analyze_budget(snapshot),
        "grade_history": historian.get_grade_history(city_name),
    }


def api_watch_status() -> dict[str, Any]:
    cfg = load_config()
    service = get_watch_service()
    return {
        "ok": True,
        "enabled": service.is_running(),
        "watch_enabled": bool(cfg.watch_enabled),
    }


def api_watch_toggle(body: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(body.get("enabled", True))
    path = set_watch_enabled(enabled=enabled)
    service = get_watch_service()
    if enabled:
        service.start()
    else:
        service.stop()
    return {"ok": True, "enabled": enabled, "config_path": str(path)}


def api_clear_chat(_body: dict[str, Any] | None = None) -> dict[str, Any]:
    get_conversation().clear()
    return {"ok": True}


def api_export_report(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    cfg = load_config_cached()
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return {"ok": False, "error": "No city export yet"}
    snapshot, err = load_export_cached(export_path)
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


def api_update_check(*, force: bool = False) -> dict[str, Any]:
    if force:
        clear_update_cache()
    result = check_for_update(force=force)
    payload = result.to_dict()
    payload["ok"] = result.ok
    return payload


def api_update_settings(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    check_on_startup = body.get("check_on_startup")
    if check_on_startup is None:
        return {"ok": False, "error": "check_on_startup is required"}
    path = save_update_settings(check_on_startup=bool(check_on_startup))
    return {"ok": True, "config_path": str(path), "check_on_startup": bool(check_on_startup)}


def api_update_dismiss(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    version = str(body.get("version", "")).strip()
    if not version:
        return {"ok": False, "error": "version is required"}
    path = dismiss_update(version)
    clear_update_cache()
    return {"ok": True, "config_path": str(path), "dismissed_version": version}


def api_update_download(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    check = check_for_update(force=bool(body.get("force")))
    if not check.ok:
        return {"ok": False, "error": check.error or "Update check failed"}
    if not check.update_available:
        return {"ok": False, "error": "No update available"}
    if not check.download_url or not check.installer_name:
        return {"ok": False, "error": "Release has no Windows installer asset"}

    try:
        path = download_installer(
            download_url=check.download_url,
            installer_name=check.installer_name,
            expected_size=check.installer_size,
        )
    except (OSError, urllib.error.URLError, RuntimeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "path": str(path),
        "latest_version": check.latest_version,
        "installer_name": check.installer_name,
    }


def api_update_install(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    raw_path = str(body.get("path", "")).strip()
    if raw_path:
        installer_path = Path(raw_path).expanduser().resolve()
        updates_root = (config_dir() / "updates").resolve()
        try:
            installer_path.relative_to(updates_root)
        except ValueError:
            return {"ok": False, "error": f"Installer must be under {updates_root}"}
    else:
        check = check_for_update(force=False)
        if not check.installer_name:
            return {"ok": False, "error": "No installer downloaded yet"}
        installer_path = (config_dir() / "updates" / check.installer_name).resolve()

    try:
        launch_installer(installer_path)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "path": str(installer_path), "quitting": True}


_FOCUS_VIEWS = frozenset({"dashboard", "insights", "issues", "ask", "settings", "feedback"})
_focus_handler: Callable[..., None] | None = None
_comayor_open: Callable[[], dict[str, Any]] | None = None
_comayor_close: Callable[[], dict[str, Any]] | None = None


def register_focus_handler(handler: Callable[..., None]) -> None:
    global _focus_handler
    _focus_handler = handler


def register_comayor_handlers(
    open_handler: Callable[[], dict[str, Any]],
    close_handler: Callable[[], dict[str, Any]],
) -> None:
    global _comayor_open, _comayor_close
    _comayor_open = open_handler
    _comayor_close = close_handler


def api_focus(view: str | None = None) -> dict[str, Any]:
    if _focus_handler is None:
        return {"ok": False, "error": "App not ready"}
    requested = (view or "").strip().lower() or None
    if requested is not None and requested not in _FOCUS_VIEWS:
        return {"ok": False, "error": f"Unsupported view: {requested}"}
    handler = _focus_handler
    if requested is None:
        handler()
    else:
        try:
            handler(view=requested)
        except TypeError:
            # Older handlers (tray / single-instance) take no kwargs.
            handler()
    return {"ok": True, "action": "focus", "view": requested}


def api_comayor_status() -> dict[str, Any]:
    cfg = load_config()
    return {"ok": True, "enabled": bool(cfg.comayor_enabled)}


def api_comayor_set(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    if "enabled" not in body:
        return {"ok": False, "error": "enabled is required"}
    enabled = bool(body["enabled"])
    path = set_comayor_enabled(enabled=enabled)
    action: dict[str, Any] = {"ok": True}
    if enabled:
        if _comayor_open is None:
            return {
                "ok": True,
                "enabled": True,
                "config_path": str(path),
                "warning": "Co-Mayor will open on next launch",
            }
        action = _comayor_open()
    else:
        if _comayor_close is not None:
            action = _comayor_close()
        else:
            action = {"ok": True}
    return {
        "ok": True,
        "enabled": enabled,
        "config_path": str(path),
        "action": action.get("action"),
        "error": None if action.get("ok", True) else action.get("error"),
        "spawn_ok": bool(action.get("ok", True)),
    }
