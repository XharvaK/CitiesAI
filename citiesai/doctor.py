from __future__ import annotations

from .config import CitiesAIConfig, config_path, load_config
from .constants import STALE_AFTER_SECONDS
from .dashboard import extract_headline_metrics
from .issues import blocking_issue_count, collect_issues
from .official_fallbacks import official_stats_degraded
from .snapshot import SnapshotMeta, load_snapshot_safe, snapshot_meta
from .status import collect_status_report
from .summary import congestion_export_notice


def _metrics_for_doctor(cfg: CitiesAIConfig) -> tuple[dict | None, dict | None, SnapshotMeta | None]:
    export_path = cfg.resolved_export_path()
    if not export_path.is_file():
        return None, None, None
    snapshot, _err = load_snapshot_safe(export_path)
    if snapshot is None:
        return None, None, None
    meta = snapshot_meta(snapshot, path=export_path)
    return extract_headline_metrics(snapshot, meta), snapshot, meta


def run_doctor(cfg: CitiesAIConfig | None = None) -> int:
    cfg = cfg or load_config()
    report = collect_status_report(cfg)
    report["mod_installed"] = mod_installed()
    metrics, snapshot, meta = _metrics_for_doctor(cfg)
    blocking = blocking_issue_count(collect_issues(report, metrics))

    print("CitiesAI doctor")
    print("===============")
    print(
        f"config: {config_path() if config_path().is_file() else '(not created - run citiesai setup)'}"
    )
    print(f"discovery source: {report['discovery_source']}")
    print("")

    print("[paths]")
    for entry in report["paths"].values():
        _print_path_entry(entry)

    print("")
    print("[export]")
    export = report.get("export")
    if export:
        print(f"  export schema: {export.get('schema_version')}")
        age = export.get("age_seconds")
        if age is not None:
            print(f"  export age: {age / 60.0:.1f} min")
        else:
            print("  export age: unknown")
        if export.get("stale"):
            print(
                f"  warning: export is stale (>{STALE_AFTER_SECONDS} sec). "
                "Load city in-game or wait for next export cycle."
            )
        if snapshot is not None and meta is not None:
            congestion_notice = congestion_export_notice(snapshot, meta)
            if congestion_notice:
                print(f"  warning: {congestion_notice}")
            if official_stats_degraded(snapshot):
                print(
                    "  warning: official city statistics export failed — "
                    "treasury/income/health may be n/a until the Data Export mod recovers. "
                    "Close CS2 and reinstall the mod from CitiesAI Settings if it persists."
                )
    else:
        print("  (no export file)")

    print("")
    print("[knowledge]")
    knowledge = report.get("knowledge", {})
    if knowledge.get("error"):
        print(f"  error loading knowledge sources: {knowledge['error']}")
    else:
        print(f"  wiki chunks: {knowledge.get('wiki_chunks')}")
        enc = knowledge.get("encyclopedia", {})
        print(f"  encyclopedia available: {enc.get('available')}")
        if not enc.get("available"):
            print(f"  encyclopedia note: {enc.get('warning', 'not found')}")

    print("")
    print("[llm]")
    llm = report.get("llm", {})
    if llm.get("configured"):
        print(f"  provider: {llm.get('provider')}")
        print(f"  model: {llm.get('model')}")
        print(f"  api key: set via {llm.get('api_key_env')}")
    else:
        print(f"  api key: not set ({llm.get('api_key_env')})")
        print("  hint: free Mistral tier at https://console.mistral.ai (SMS verification)")
    print("")

    if blocking:
        print(f"Result: {blocking} issue(s) found.")
        return 1
    print("Result: OK")
    return 0


def _print_path_entry(entry: dict) -> None:
    label = entry.get("label", "path")
    path = entry.get("path")
    if path is None:
        print(f"  {label}: missing")
        return
    print(f"  {label}: {path}")
    if not entry.get("ok") and entry.get("error"):
        print(f"    error: {entry['error']}")
