from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ask_core import run_ask
from .config import apply_config_to_env, load_config
from .diff import diff_snapshots, format_diff_markdown, resolve_snapshot_path
from .doctor import run_doctor
from .gui.server import run_gui
from .historian import get_historian
from .keywords import build_search_queries
from .knowledge import format_knowledge_bundle, retrieve_knowledge
from .mcp_server import run_mcp_server
from .report_html import write_report_file
from .setup_wizard import run_setup
from .snapshot import load_snapshot_safe, snapshot_meta
from .summary import build_city_brief
from .version import __version__
from .watch import WatchService


def _resolved_export_path(args: argparse.Namespace) -> Path:
    cfg = load_config()
    return (args.export or cfg.resolved_export_path()).expanduser()


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _export_dir(args: argparse.Namespace) -> Path:
    cfg = load_config()
    return (args.export or cfg.resolved_export_path()).expanduser().parent


def _cmd_context(args: argparse.Namespace) -> int:
    cfg = load_config()
    export_path: Path = (args.export or cfg.resolved_export_path()).expanduser()
    if not export_path.is_file():
        print(f"Export not found: {export_path}", file=sys.stderr)
        print("Load a city in CS2 with CS2 Data Export enabled.", file=sys.stderr)
        return 2

    snapshot, err = load_snapshot_safe(export_path)
    if snapshot is None:
        print(err or f"Export not readable: {export_path}", file=sys.stderr)
        print("Load a city in CS2 with CS2 Data Export enabled.", file=sys.stderr)
        return 2
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
    snapshot, _ = load_snapshot_safe(export_path) if export_path.is_file() else (None, None)
    snapshot = snapshot or {}

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
        agentic=not args.no_agentic,
        write_advice_file=args.write_advice,
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
            "encyclopedia evidence. Cite sources."
        )
        return 0

    if result.get("answer"):
        print(f"# Answer: {args.question}\n")
        print(result["answer"])
        if result.get("sources") and args.show_sources:
            print("\n## Sources")
            for src in result["sources"][:10]:
                title = src.get("title") or src.get("tool") or src.get("source")
                print(f"- {title}")
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
    return run_gui(
        host=args.host,
        port=args.port,
        window=window,
        hud=args.hud,
        watch=args.watch,
    )


def _cmd_history(args: argparse.Namespace) -> int:
    historian = get_historian()
    result = historian.sync()
    history = historian.get_history(limit=args.limit, export_path=args.export)
    print(f"Historian DB: {result['db_path']} (+{result['ingested']} ingested)")
    print(f"City: {history['city_name']} ({history['count']} points)")
    if args.digest:
        digest = historian.session_digest(export_path=args.export)
        if digest.get("has_changes"):
            print("\n## Since last session")
            for line in digest["summary"]:
                print(f"- {line}")
    if args.anomalies:
        for row in historian.detect_anomalies(export_path=args.export):
            print(f"- [{row['severity']}] {row['title']}: {row['detail']}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    export_dir = _export_dir(args)
    try:
        path_a = resolve_snapshot_path(args.before, export_dir=export_dir)
        path_b = resolve_snapshot_path(args.after, export_dir=export_dir)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    snap_a, err_a = load_snapshot_safe(path_a)
    snap_b, err_b = load_snapshot_safe(path_b)
    if snap_a is None:
        print(err_a or f"Unreadable: {path_a}", file=sys.stderr)
        return 2
    if snap_b is None:
        print(err_b or f"Unreadable: {path_b}", file=sys.stderr)
        return 2
    result = diff_snapshots(snap_a, snap_b, path_a=path_a, path_b=path_b)
    print(format_diff_markdown(result))
    return 0


def _cmd_transit(args: argparse.Namespace) -> int:
    from .analyzers.transit import analyze_transit_lines

    path = _resolved_export_path(args)
    if not path.is_file():
        print(f"Export not found: {path}", file=sys.stderr)
        return 2
    snapshot, err = load_snapshot_safe(path)
    if snapshot is None:
        print(err or f"Export not readable: {path}", file=sys.stderr)
        return 2
    report = analyze_transit_lines(snapshot)
    print(f"# Transit Line Doctor\n\n{report.get('summary', '')}\n")

    groups = report.get("problem_groups") or []
    if groups:
        print("## Problem groups\n")
        for group in groups:
            modes = group.get("modes") or {}
            mode_text = ", ".join(f"{mode} {count}" for mode, count in sorted(modes.items()))
            print(
                f"### {group['title']} ({group['line_count']} lines, {group['severity']})"
            )
            print(group["diagnosis"])
            if mode_text:
                print(f"- modes: {mode_text}")
            if group.get("total_waiting"):
                print(f"- waiting: {group['total_waiting']:,}")
            if group.get("action"):
                print(f"- action: {group['action']}")
            print("")

    if args.lines:
        print("## All lines\n")
        for line in report.get("lines", []):
            print(f"### {line['line_name']} ({line['mode']}) — {line['severity']}")
            print(line["diagnosis"])
            if line.get("issues"):
                for issue in line["issues"]:
                    print(f"- {issue}")
            print("")
    elif groups:
        print("Use `citiesai transit --lines` to list every line.\n")
    elif report.get("lines"):
        for line in report.get("lines", []):
            if line.get("severity") == "ok":
                continue
            print(f"## {line['line_name']} ({line['mode']}) — {line['severity']}")
            print(line["diagnosis"])
            if line.get("issues"):
                for issue in line["issues"]:
                    print(f"- {issue}")
            print("")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from .report_ops import build_and_persist_report_card

    path = _resolved_export_path(args)
    if not path.is_file():
        print(f"Export not found: {path}", file=sys.stderr)
        return 2
    snapshot, err = load_snapshot_safe(path)
    if snapshot is None:
        print(err or f"Export not readable: {path}", file=sys.stderr)
        return 2
    meta = snapshot_meta(snapshot, path=path)
    card = build_and_persist_report_card(snapshot, meta)
    if args.format == "html":
        out = Path(args.output) if args.output else Path.cwd() / "citiesai-report.html"
        write_report_file(snapshot, meta, out)
        print(f"Wrote {out}")
        return 0
    print(f"# City Report Card — {card.get('city_name')}\n")
    print(f"Overall: **{card['overall_grade']}** ({card['overall_score']}/100)\n")
    for domain in card["domains"]:
        delta = f" ({domain['grade_delta']})" if domain.get("grade_delta") else ""
        print(f"- {domain['label']}: {domain['grade']}{delta} — {domain.get('detail', '')}")
    return 0


def _cmd_watch(args: argparse.Namespace) -> int:
    service = WatchService(interval_seconds=args.interval, use_toast=not args.no_toast)
    print(f"Watch mode — polling every {args.interval}s (Ctrl+C to stop)")
    try:
        while True:
            alerts = service.tick()
            for alert in alerts:
                print(f"[{alert['title']}] {alert['message']}")
            import time

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def _cmd_brief(args: argparse.Namespace) -> int:
    from .briefing import build_mayors_briefing

    path = _resolved_export_path(args)
    if not path.is_file():
        print(f"Export not found: {path}", file=sys.stderr)
        return 2
    snapshot, err = load_snapshot_safe(path)
    if snapshot is None:
        print(err or f"Export not readable: {path}", file=sys.stderr)
        return 2
    meta = snapshot_meta(snapshot, path=path)
    historian = get_historian()
    historian.sync(path)
    briefing = build_mayors_briefing(snapshot, meta, historian=historian)
    print(briefing.get("text") or "No briefing content yet.")
    return 0


def _cmd_mcp(_args: argparse.Namespace) -> int:
    return run_mcp_server()


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
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
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
    ask.add_argument("--no-llm", action="store_true", help="Print prompt bundle only")
    ask.add_argument("--no-agentic", action="store_true", help="Disable tool-calling agent loop")
    ask.add_argument("--show-sources", action="store_true", help="Print retrieval sources")
    ask.add_argument("--write-advice", action="store_true", help="Write advice.json for in-game companion")
    ask.set_defaults(func=_cmd_ask)

    setup = sub.add_parser("setup", help="Detect paths and write config")
    setup.add_argument("-y", "--yes", action="store_true", help="Non-interactive; accept detected paths")
    setup.set_defaults(func=_cmd_setup)

    doctor = sub.add_parser("doctor", help="Verify paths, export, and knowledge sources")
    doctor.set_defaults(func=_cmd_doctor)

    gui = sub.add_parser("gui", help="Local desktop app (dashboard, ask, settings)")
    gui.add_argument("--host", default="127.0.0.1")
    gui.add_argument("--port", type=int, default=8765)
    gui.add_argument("--browser", action="store_true")
    gui.add_argument("--no-window", action="store_true")
    gui.add_argument("--hud", action="store_true", help="Also open mini HUD overlay")
    gui.add_argument("--watch", action="store_true", help="Enable background watch alerts")
    gui.set_defaults(func=_cmd_gui)

    history = sub.add_parser("history", help="Persistent city historian (SQLite)")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--digest", action="store_true", help="Show since-last-session digest")
    history.add_argument("--anomalies", action="store_true", help="List detected anomalies")
    history.set_defaults(func=_cmd_history)

    diff = sub.add_parser("diff", help="Compare two export snapshots")
    diff.add_argument("before", help="Earlier snapshot path, filename, or 'latest'")
    diff.add_argument("after", help="Later snapshot path, filename, or 'latest'")
    diff.set_defaults(func=_cmd_diff)

    transit = sub.add_parser("transit", help="Transit Line Doctor report")
    transit.add_argument(
        "--lines",
        action="store_true",
        help="List every line after the grouped summary",
    )
    transit.set_defaults(func=_cmd_transit)

    report = sub.add_parser("report", help="City Report Card")
    report.add_argument("--format", choices=("text", "html"), default="text")
    report.add_argument("-o", "--output", help="Output path for HTML report")
    report.set_defaults(func=_cmd_report)

    brief = sub.add_parser("brief", help="Mayor's briefing for the current city")
    brief.set_defaults(func=_cmd_brief)

    watch = sub.add_parser("watch", help="Background threshold alerts")
    watch.add_argument("--interval", type=float, default=15.0)
    watch.add_argument("--no-toast", action="store_true")
    watch.set_defaults(func=_cmd_watch)

    mcp = sub.add_parser("mcp", help="Run CitiesAI MCP server (stdio)")
    mcp.set_defaults(func=_cmd_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    apply_config_to_env(load_config())
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
