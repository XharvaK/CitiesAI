from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import CitiesAIConfig, load_config
from .keywords import build_search_queries
from .knowledge import format_knowledge_bundle, retrieve_knowledge
from .llm import generate_answer
from .snapshot import SnapshotMeta, load_snapshot, snapshot_meta
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

    snapshot = load_snapshot(path)
    meta = snapshot_meta(snapshot, path=path)
    bundle = build_ask_bundle(snapshot, meta, question, limit=limit)
    payload: dict[str, Any] = {
        "ok": True,
        "question": question,
        "meta": meta_to_dict(meta),
        "bundle": bundle,
    }

    if not use_llm:
        payload["mode"] = "bundle"
        payload["answer"] = None
        return payload

    try:
        answer = generate_answer(bundle, cfg=cfg)
    except RuntimeError as exc:
        payload["mode"] = "bundle"
        payload["answer"] = None
        payload["llm_error"] = str(exc)
        return payload

    payload["mode"] = "llm"
    payload["answer"] = answer
    return payload
