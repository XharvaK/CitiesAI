from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ask_core import run_ask
from .config import apply_config_to_env, load_config
from .doctor import run_doctor
from .gui.server import run_gui
from .keywords import build_search_queries
from .knowledge import format_knowledge_bundle, retrieve_knowledge
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
    result = run_ask(
        args.question,
        use_llm=not args.no_llm,
        limit=args.limit,
        export_path=(args.export or load_config().resolved_export_path()).expanduser(),
    )
    if not result.get("ok"):
        print(result.get("error", "Ask failed."), file=sys.stderr)
        if hint := result.get("hint"):
            print(hint, file=sys.stderr)
        return 2

    bundle = result["bundle"]
    if args.no_llm:
        print(bundle)
        print("")
        print("## Answer guidance")
        print(
            "Synthesize one practical answer using the city brief numbers first, then wiki and "
            "encyclopedia evidence. Call out stale snapshot data if age > 90 sec. Cite sources."
        )
        return 0

    if result.get("answer"):
        print(f"# Answer: {args.question}\n")
        print(result["answer"])
        return 0

    print(bundle)
    print("")
    print("## LLM unavailable")
    print(result.get("llm_error", "Unknown error"))
    print("")
    print("Use --no-llm to print this bundle for Cursor or another agent.")
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    return run_setup(non_interactive=args.yes)


def _cmd_doctor(_args: argparse.Namespace) -> int:
    return run_doctor()


def _cmd_gui(args: argparse.Namespace) -> int:
    if args.browser:
        window = "browser"
    elif args.no_window:
        window = "none"
    else:
        window = "native"
    return run_gui(host=args.host, port=args.port, window=window)


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

    gui = sub.add_parser("gui", help="Local desktop app (dashboard, ask, settings)")
    gui.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    gui.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    gui.add_argument(
        "--browser",
        action="store_true",
        help="Open in external browser instead of the app window",
    )
    gui.add_argument(
        "--no-window",
        action="store_true",
        help="Run HTTP server only (no app window)",
    )
    gui.set_defaults(func=_cmd_gui)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    apply_config_to_env(load_config())
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
