from __future__ import annotations

from pathlib import Path
from typing import Any

from .advice_output import write_advice
from .config import CitiesAIConfig, load_config
from .conversation import get_conversation
from .keywords import build_search_queries
from .knowledge import format_knowledge_bundle, retrieve_knowledge
from .llm import generate_agentic_answer, generate_answer
from .snapshot import SnapshotMeta, load_snapshot_safe, snapshot_meta
from .summary import build_city_brief


def meta_to_dict(meta: SnapshotMeta) -> dict[str, Any]:
    return {
        "path": str(meta.path),
        "schema_version": meta.schema_version,
        "exported_at_utc": meta.exported_at_utc,
        "city_name": meta.city_name,
        "age_seconds": meta.age_seconds,
        "stale": meta.stale,
    }


def collect_sources_for_queries(queries: list[str], *, limit: int = 5) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for query in queries:
        bundle = retrieve_knowledge(query, limit=limit)
        for hit in bundle.wiki_hits:
            sources.append(
                {
                    "source": "wiki",
                    "title": hit.get("title"),
                    "url": hit.get("url"),
                    "snippet": hit.get("snippet", "")[:300],
                    "query": query,
                }
            )
        for hit in bundle.encyclopedia_hits:
            sources.append(
                {
                    "source": "encyclopedia",
                    "title": hit.get("title"),
                    "snippet": hit.get("snippet", "")[:300],
                    "query": query,
                }
            )
    return sources[:20]


def build_ask_bundle(
    snapshot: dict[str, Any],
    meta: SnapshotMeta,
    question: str,
    *,
    limit: int = 5,
) -> str:
    parts: list[str] = [build_city_brief(snapshot, meta), "", f"## Question\n{question}\n"]
    queries = build_search_queries(snapshot, question)

    for index, query in enumerate(queries):
        if index:
            parts.append("\n---\n")
        bundle = retrieve_knowledge(query, limit=limit)
        parts.append(format_knowledge_bundle(bundle, query))

    return "\n".join(parts)


def run_ask(
    question: str,
    *,
    use_llm: bool = True,
    limit: int = 5,
    export_path: Path | None = None,
    cfg: CitiesAIConfig | None = None,
    agentic: bool = True,
    multi_turn: bool = True,
    write_advice_file: bool = False,
) -> dict[str, Any]:
    cfg = cfg or load_config()
    path = (export_path or cfg.resolved_export_path()).expanduser()
    if not path.is_file():
        return {
            "ok": False,
            "error": f"Export not found: {path}",
            "hint": "Load a city in CS2 with CS2 Data Export enabled.",
        }

    question = question.strip()
    if not question:
        return {"ok": False, "error": "Question is required."}

    snapshot, err = load_snapshot_safe(path)
    if snapshot is None:
        return {
            "ok": False,
            "error": err or f"Export not readable: {path}",
            "hint": "Load a city in CS2 with CS2 Data Export enabled.",
        }
    meta = snapshot_meta(snapshot, path=path)
    brief = build_city_brief(snapshot, meta)
    bundle = build_ask_bundle(snapshot, meta, question, limit=limit)
    queries = build_search_queries(snapshot, question)
    retrieval_sources = collect_sources_for_queries(queries, limit=limit)

    conv = get_conversation()
    if multi_turn:
        conv.set_city_header(brief)

    payload: dict[str, Any] = {
        "ok": True,
        "question": question,
        "meta": meta_to_dict(meta),
        "bundle": bundle,
        "sources": retrieval_sources,
    }

    if not use_llm:
        payload["mode"] = "bundle"
        payload["answer"] = None
        return payload

    try:
        if agentic:
            history = conv.messages_for_llm() if multi_turn else None
            result = generate_agentic_answer(
                question,
                city_brief=brief,
                snapshot=snapshot,
                cfg=cfg,
                history_messages=history,
            )
            answer = result.answer
            all_sources = retrieval_sources + [
                {"source": "tool", "title": name, "snippet": ""} for name in result.tool_calls
            ]
            payload["sources"] = all_sources
            payload["tool_calls"] = result.tool_calls
        else:
            answer = generate_answer(bundle, cfg=cfg)
    except RuntimeError as exc:
        payload["mode"] = "bundle"
        payload["answer"] = None
        payload["llm_error"] = str(exc)
        return payload

    if multi_turn:
        conv.add_turn("user", question)
        conv.add_turn("assistant", answer, sources=payload.get("sources", []))

    if write_advice_file:
        write_advice(title=question[:80], body=answer, export_path=path)

    payload["mode"] = "llm"
    payload["answer"] = answer
    payload["agentic"] = agentic
    return payload
