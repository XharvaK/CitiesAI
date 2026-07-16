"""Mayor's Briefing — session-start summary for the current city."""

from __future__ import annotations

from typing import Any

from .analyzers.report_card import build_report_card
from .city_issues import detect_city_issues
from .forecasts import build_forecasts
from .historian import CityHistorian, get_historian
from .snapshot import SnapshotMeta


def _severity_rank(severity: str) -> int:
    return {"error": 0, "warn": 1, "info": 2}.get(severity, 9)


def _top_issues(issues: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    city_issues = [issue for issue in issues if issue.get("kind") == "city"]
    city_issues.sort(
        key=lambda issue: (
            _severity_rank(str(issue.get("severity", "info"))),
            -(issue.get("session_count") or 1),
        )
    )
    return city_issues[:limit]


def _format_lines(sections: list[str]) -> str:
    return "\n".join(line for line in sections if line.strip())


def build_mayors_briefing(
    snapshot: dict[str, Any],
    meta: SnapshotMeta,
    *,
    historian: CityHistorian | None = None,
    history: dict[str, Any] | None = None,
    issues: list[dict[str, Any]] | None = None,
    report_card: dict[str, Any] | None = None,
    forecasts: dict[str, Any] | None = None,
    digest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hist = historian or get_historian()
    history = history or hist.get_history(export_path=meta.path)
    digest = digest if digest is not None else hist.session_digest(history=history)
    resolved = hist.get_resolved_since_last_session(history=history)
    issues = issues or detect_city_issues(snapshot)
    issues = hist.enrich_issues_with_lifecycle(issues, city_name=history.get("city_name"))
    top_issues = _top_issues(issues)
    forecasts = forecasts if forecasts is not None else build_forecasts(history)
    report_card = report_card or build_report_card(
        snapshot,
        meta,
        previous_domain_scores=hist.previous_session_report_scores(
            str(history.get("city_name") or ""),
            history=history,
        ),
    )

    grade_deltas = [
        {
            "label": domain["label"],
            "grade": domain["grade"],
            "delta": domain.get("grade_delta"),
        }
        for domain in report_card.get("domains", [])
        if domain.get("grade_delta")
    ]

    lines: list[str] = [f"# Mayor's briefing — {history.get('city_name', 'Your city')}"]
    if digest.get("has_changes") and digest.get("summary"):
        lines.append("")
        lines.append("## Since last session")
        for item in digest["summary"]:
            lines.append(f"- {item}")

    if resolved:
        lines.append("")
        lines.append("## Resolved")
        for item in resolved:
            lines.append(f"- {item['title']} ✓")

    if top_issues:
        lines.append("")
        lines.append("## Priorities")
        for issue in top_issues:
            age = ""
            if issue.get("session_count", 1) > 1:
                age = f" (ongoing {issue['session_count']} sessions)"
            lines.append(f"- **{issue['title']}**{age}: {issue.get('detail', '')}")

    if forecasts.get("alerts"):
        lines.append("")
        lines.append("## Forecasts")
        for alert in forecasts["alerts"][:3]:
            lines.append(f"- {alert}")

    if grade_deltas:
        lines.append("")
        lines.append("## Grade changes")
        for row in grade_deltas:
            lines.append(f"- {row['label']}: {row['grade']} ({row['delta']})")

    text = _format_lines(lines)
    return {
        "city_name": history.get("city_name"),
        "has_content": bool(
            digest.get("has_changes")
            or resolved
            or top_issues
            or forecasts.get("alerts")
            or grade_deltas
        ),
        "digest": digest,
        "resolved": resolved,
        "top_issues": top_issues,
        "forecasts": forecasts,
        "grade_deltas": grade_deltas,
        "report_card": {
            "overall_grade": report_card.get("overall_grade"),
            "overall_score": report_card.get("overall_score"),
        },
        "text": text,
    }
