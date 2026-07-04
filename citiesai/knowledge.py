from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cities2_mcp import bundled_data_dir
from cities2_mcp.game_encyclopedia import EncyclopediaConfig, GameEncyclopediaSource
from cities2_mcp.retrieval import Corpus

from .config import load_config

JsonDict = dict[str, Any]

_cached_wiki_corpus: Corpus | None = None
_cached_encyclopedia: GameEncyclopediaSource | None = None


@dataclass
class KnowledgeBundle:
    wiki_status: str
    encyclopedia_status: str
    encyclopedia_available: bool
    wiki_hits: list[JsonDict]
    encyclopedia_hits: list[JsonDict]


def reset_knowledge_cache() -> None:
    global _cached_wiki_corpus, _cached_encyclopedia
    _cached_wiki_corpus = None
    _cached_encyclopedia = None


def _wiki_corpus() -> Corpus:
    global _cached_wiki_corpus
    if _cached_wiki_corpus is None:
        _cached_wiki_corpus = Corpus([bundled_data_dir()])
    return _cached_wiki_corpus


def _encyclopedia() -> GameEncyclopediaSource:
    global _cached_encyclopedia
    if _cached_encyclopedia is not None:
        return _cached_encyclopedia

    cfg = load_config()
    cache_raw = os.environ.get("CITIES2_ENCYCLOPEDIA_CACHE_DIR") or os.environ.get(
        "CITIESAI_ENCYCLOPEDIA_CACHE_DIR"
    )
    cache_dir = Path(cache_raw).expanduser() if cache_raw else None
    config = EncyclopediaConfig(
        game_dir=cfg.resolved_game_dir(),
        locale_cok=cfg.resolved_locale_cok(),
        cache_dir=cache_dir,
    )
    _cached_encyclopedia = GameEncyclopediaSource.load(config)
    return _cached_encyclopedia


def retrieve_knowledge(query: str, *, limit: int = 5) -> KnowledgeBundle:
    corpus = _wiki_corpus()
    encyclopedia = _encyclopedia()

    wiki_hits: list[JsonDict] = []
    for score, chunk in corpus.search_chunks(query, limit=limit):
        wiki_hits.append(
            {
                "score": round(score, 4),
                "source": "wiki",
                "page_id": chunk.get("page_id"),
                "title": chunk.get("title"),
                "url": chunk.get("url"),
                "snippet": str(chunk.get("text", ""))[:900],
            }
        )

    encyclopedia_hits = encyclopedia.search(query, limit=limit) if encyclopedia.available else []

    wiki_status = "ok" if wiki_hits else "no_hits"

    enc_status = encyclopedia.status()
    encyclopedia_status = "ok" if encyclopedia_hits else (
        "unavailable" if not encyclopedia.available else "no_hits"
    )

    return KnowledgeBundle(
        wiki_status=wiki_status,
        encyclopedia_status=encyclopedia_status,
        encyclopedia_available=bool(enc_status.get("available")),
        wiki_hits=wiki_hits,
        encyclopedia_hits=encyclopedia_hits,
    )


def format_knowledge_bundle(bundle: KnowledgeBundle, query: str) -> str:
    lines = [f"## Knowledge retrieval: `{query}`", ""]
    lines.append(f"- wiki: {bundle.wiki_status}")
    lines.append(f"- encyclopedia: {bundle.encyclopedia_status}")
    lines.append("")

    if bundle.wiki_hits:
        lines.append("### Wiki")
        for hit in bundle.wiki_hits:
            title = hit.get("title") or hit.get("page_id")
            url = hit.get("url") or ""
            snippet = str(hit.get("snippet", "")).strip().replace("\n", " ")
            if len(snippet) > 280:
                snippet = snippet[:277] + "..."
            lines.append(f"- **{title}** ({url})")
            if snippet:
                lines.append(f"  {snippet}")
        lines.append("")

    if bundle.encyclopedia_hits:
        lines.append("### Game Encyclopedia")
        for hit in bundle.encyclopedia_hits:
            title = hit.get("title") or hit.get("entry_id")
            tab = hit.get("tab")
            suffix = f" - {tab}" if tab else ""
            snippet = str(hit.get("snippet", "")).strip().replace("\n", " ")
            if len(snippet) > 280:
                snippet = snippet[:277] + "..."
            lines.append(f"- **{title}**{suffix}")
            if snippet:
                lines.append(f"  {snippet}")
        lines.append("")

    if not bundle.wiki_hits and not bundle.encyclopedia_hits:
        lines.append("_No hits. Try a shorter mechanic-focused query._")
        lines.append("")

    return "\n".join(lines)


def knowledge_status() -> dict[str, Any]:
    corpus = _wiki_corpus()
    encyclopedia = _encyclopedia()
    return {
        "wiki_chunks": len(corpus.chunks),
        "encyclopedia": encyclopedia.status(),
    }
