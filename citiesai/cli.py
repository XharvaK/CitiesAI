from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import apply_config_to_env, load_config
from .doctor import run_doctor
from .keywords import build_search_queries
from .knowledge import format_knowledge_bundle, retrieve_knowledge
from .llm import generate_answer
from .setup_wizard import run_setup
from .snapshot import load_snapshot, snapshot_meta
from .summary import build_city_brief


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _build_ask_bundle(snapshot: dict, meta, question: str, *, limit: int) -> str:
    parts: list[str] = [build_city_brief(snapshot, meta), "", f"## Question\n{question}\n"]
    queries = build_search_queries(snapshot, question)
    parts.append("## Retrieval plan")
    for query in queries:
        parts.append(f"- `{query}`")
    parts.append("")

    for index, query in enumerate(queries):
        if index:
            parts.append("\n---\n")
        bundle = retrieve_knowledge(query, limit=limit)
        parts.append(format_knowledge_bundle(bundle, query))

    return "\n".join(parts)


def _cmd_context(args: argparse.Namespace) -> int:
    cfg = load_config()
    export_path: Path = (args.export or cfg.resolved_export_path()).expanduser()
    if not export_path.is_file():
        print(f"Export not found: {export_path}", file=sys.stderr)
        print("Load a city in CS2 with CS2 Data Export enabled.", file=sys.stderr)
        return 2

    snapshot = load_snapshot(export_path)
    meta = snapshot_meta(snapshot, path=export_path)
    print(build_city_brief(snapshot, meta))

    if args.question:
        queries = build_search_queries(snapshot, args.question)
        print("")
        print("## Suggested search queries")
        for query in queries:
            print(f"- `{query}`")
    return 0


def _cmd_retrieve(args: argparse.Namespace) -> int:
    cfg = load_config()
    export_path: Path = (args.export or cfg.resolved_export_path()).expanduser()
    snapshot = load_snapshot(export_path) if export_path.is_file() else {}

    queries: list[str] = []
    if args.query:
        queries = [args.query]
    elif args.question:
        queries = build_search_queries(snapshot, args.question)
    else:
        print("Provide --query or --question.", file=sys.stderr)
        return 2

    for index, query in enumerate(queries):
        if index:
            print("\n---\n")
        bundle = retrieve_knowledge(query, limit=args.limit)
        print(format_knowledge_bundle(bundle, query))
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    cfg = load_config()
    export_path: Path = (args.export or cfg.resolved_export_path()).expanduser()
    if not export_path.is_file():
        print(f"Export not found: {export_path}", file=sys.stderr)
        return 2
    if not args.question:
        print("Provide a question.", file=sys.stderr)
        return 2

    snapshot = load_snapshot(export_path)
    meta = snapshot_meta(snapshot, path=export_path)
    bundle = _build_ask_bundle(snapshot, meta, args.question, limit=args.limit)

    if args.no_llm:
        print(bundle)
        print("")
        print("## Answer guidance")
        print(
            "Synthesize one practical answer using the city brief numbers first, then wiki and "
            "encyclopedia evidence. Call out stale snapshot data if age > 11 min. Cite sources."
        )
        return 0

    try:
        answer = generate_answer(bundle, cfg=cfg)
    except RuntimeError as exc:
        print(bundle)
        print("")
        print("## LLM unavailable")
        print(str(exc))
        print("")
        print("Use --no-llm to print this bundle for Cursor or another agent.")
        return 0

    print(f"# Answer: {args.question}\n")
    print(answer)
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    return run_setup(non_interactive=args.yes)


def _cmd_doctor(_args: argparse.Namespace) -> int:
    return run_doctor()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="citiesai",
        description="Read-only Cities: Skylines II advisor - city snapshot + local knowledge retrieval.",
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=None,
        help="Path to CS2DataExport latest.json (overrides config)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    context = sub.add_parser("context", help="Print compact city brief from latest.json")
    context.add_argument("-q", "--question", help="Optional question to suggest search queries")
    context.set_defaults(func=_cmd_context)

    retrieve = sub.add_parser("retrieve", help="Run local wiki + encyclopedia retrieval")
    retrieve.add_argument("--query", help="Explicit compact search query")
    retrieve.add_argument("-q", "--question", help="Natural-language question (derives queries)")
    retrieve.add_argument("--limit", type=int, default=5)
    retrieve.set_defaults(func=_cmd_retrieve)

    ask = sub.add_parser("ask", help="City brief + retrieval + optional LLM answer")
    ask.add_argument("question")
    ask.add_argument("--limit", type=int, default=5)
    ask.add_argument(
        "--no-llm",
        action="store_true",
        help="Print prompt bundle only (for Cursor/agents); skip LLM call",
    )
    ask.set_defaults(func=_cmd_ask)

    setup = sub.add_parser("setup", help="Detect paths and write config")
    setup.add_argument("-y", "--yes", action="store_true", help="Non-interactive; accept detected paths")
    setup.set_defaults(func=_cmd_setup)

    doctor = sub.add_parser("doctor", help="Verify paths, export, and knowledge sources")
    doctor.set_defaults(func=_cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    apply_config_to_env(load_config())
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
