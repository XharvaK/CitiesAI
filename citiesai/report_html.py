"""Generate shareable HTML city reports."""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .analyzers import analyze_budget, analyze_housing_labor, analyze_transit_lines
from .city_issues import detect_city_issues
from .dashboard import extract_headline_metrics
from .issue_advisor import enrich_issues, rank_issues_for_queue
from .report_ops import build_and_persist_report_card
from .snapshot import SnapshotMeta


def _list_items(rows: list[str], empty: str) -> str:
    if not rows:
        return f'<li class="muted">{html.escape(empty)}</li>'
    return "".join(f"<li>{row}</li>" for row in rows)


def render_report_html(
    snapshot: dict[str, Any],
    meta: SnapshotMeta,
) -> str:
    metrics = extract_headline_metrics(snapshot, meta)
    report = build_and_persist_report_card(snapshot, meta)
    budget = analyze_budget(snapshot)
    housing = analyze_housing_labor(snapshot)
    transit = analyze_transit_lines(snapshot)
    raw_issues = detect_city_issues(snapshot)
    ranked = rank_issues_for_queue(enrich_issues(raw_issues))
    city = html.escape(str(metrics.get("city_name") or "Your city"))
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    overall = html.escape(str(report.get("overall_grade") or "n/a"))
    overall_score = report.get("overall_score")
    score_text = f"{overall_score:.0f}" if isinstance(overall_score, (int, float)) else "n/a"

    domain_rows = ""
    for domain in report.get("domains") or []:
        delta = domain.get("grade_delta")
        delta_html = f' <span class="delta">{html.escape(str(delta))}</span>' if delta else ""
        domain_rows += f"""
        <tr>
          <td>{html.escape(str(domain.get("label") or ""))}</td>
          <td class="grade grade-{html.escape(str(domain.get("grade") or ""))}">{html.escape(str(domain.get("grade") or ""))}</td>
          <td class="mono">{domain.get("score", 0):.0f}</td>
          <td class="muted">{html.escape(str(domain.get("detail", "")))}{delta_html}</td>
        </tr>"""

    priority_items: list[str] = []
    for issue in ranked[:6]:
        severity = str(issue.get("severity") or "info")
        sev_label = {"error": "Critical", "warn": "Warning", "info": "Info"}.get(
            severity, severity.title()
        )
        actions = issue.get("actions") or []
        action = html.escape(str(actions[0])) if actions else ""
        action_html = f'<div class="action">Next: {action}</div>' if action else ""
        priority_items.append(
            f'<li class="priority severity-{html.escape(severity)}">'
            f'<div class="sev">{html.escape(sev_label)}</div>'
            f"<strong>{html.escape(str(issue.get('title') or ''))}</strong>"
            f'<div class="muted">{html.escape(str(issue.get("detail") or ""))}</div>'
            f"{action_html}</li>"
        )

    transit_items = [
        (
            f"<strong>{html.escape(str(group.get('title') or ''))}</strong> "
            f"({group.get('line_count', 0)} lines, {html.escape(str(group.get('severity') or ''))}): "
            f"{html.escape(str(group.get('diagnosis') or ''))}"
        )
        for group in (transit.get("problem_groups") or [])[:6]
    ]
    housing_items = [
        f"<strong>{html.escape(str(f.get('title') or ''))}</strong> — "
        f"{html.escape(str(f.get('detail') or ''))}"
        for f in (housing.get("findings") or [])[:6]
    ]
    budget_items = [
        f"<strong>{html.escape(str(f.get('title') or ''))}</strong> — "
        f"{html.escape(str(f.get('detail') or ''))}"
        for f in (budget.get("findings") or [])[:6]
    ]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CitiesAI Report — {city}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #14120e;
      --surface: #1a1711;
      --border: #3a342a;
      --ink: #f2ead3;
      --body: #d8d0be;
      --muted: #9a9080;
      --ok: #8faa7a;
      --warn: #c4a05a;
      --bad: #b53737;
      --font: "Segoe UI", system-ui, sans-serif;
      --mono: "Cascadia Mono", Consolas, monospace;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 2rem 1.25rem 3rem;
      font-family: var(--font);
      color: var(--body);
      background:
        linear-gradient(rgba(58,52,42,0.12) 1px, transparent 1px),
        linear-gradient(90deg, rgba(58,52,42,0.12) 1px, transparent 1px),
        var(--bg);
      background-size: 28px 28px, 28px 28px, auto;
      line-height: 1.45;
    }}
    main {{ max-width: 880px; margin: 0 auto; }}
    h1, h2 {{ color: var(--ink); letter-spacing: 0.02em; }}
    h1 {{ margin: 0 0 .35rem; font-size: 1.75rem; }}
    h2 {{
      margin: 0 0 .75rem;
      font-size: 1.05rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      font-weight: 650;
    }}
    .muted {{ color: var(--muted); }}
    .mono {{ font-family: var(--mono); }}
    .section {{
      border: 1px solid var(--border);
      background: rgba(26, 23, 17, 0.88);
      border-radius: 6px;
      padding: 1.1rem 1.25rem;
      margin-bottom: 0.9rem;
    }}
    .overall {{
      font-family: var(--mono);
      font-size: 2.2rem;
      font-weight: 700;
      color: var(--ink);
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: .55rem .2rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
    th {{ color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; }}
    .grade {{ font-family: var(--mono); font-weight: 700; }}
    .grade-A {{ color: var(--ok); }} .grade-B {{ color: #b5ab95; }}
    .grade-C {{ color: var(--warn); }} .grade-D {{ color: #d4956a; }} .grade-F {{ color: var(--bad); }}
    .delta {{ color: var(--muted); font-size: .85rem; }}
    ul {{ margin: .35rem 0 0; padding-left: 1.1rem; }}
    .priority-list {{ list-style: none; padding: 0; margin: 0; }}
    .priority {{
      border-left: 3px solid var(--muted);
      padding: .55rem .75rem;
      margin: 0 0 .55rem;
      background: rgba(20, 18, 14, 0.55);
    }}
    .priority.severity-error {{ border-left-color: var(--bad); }}
    .priority.severity-warn {{ border-left-color: var(--warn); }}
    .priority.severity-info {{ border-left-color: var(--ok); }}
    .sev {{
      font-family: var(--mono);
      font-size: .72rem;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: .2rem;
    }}
    .action {{ margin-top: .35rem; color: var(--ink); font-size: .92rem; }}
    footer {{ margin-top: 1.5rem; color: var(--muted); font-size: .85rem; }}
    @media print {{
      body {{ background: #14120e; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      .section {{ break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="section">
      <h1>{city}</h1>
      <p class="muted">Civic briefing · Generated {generated} · Export {html.escape(str(meta.exported_at_utc or "n/a"))}</p>
      <p>Overall <span class="overall grade grade-{overall}">{overall}</span>
         <span class="mono">({score_text}/100)</span></p>
      <p class="muted">{html.escape(str(budget.get("summary") or ""))}</p>
    </header>

    <section class="section" aria-labelledby="priorities-heading">
      <h2 id="priorities-heading">Priorities</h2>
      <ul class="priority-list">
        {"".join(priority_items) or '<li class="muted">No major priorities detected.</li>'}
      </ul>
    </section>

    <section class="section" aria-labelledby="report-card-heading">
      <h2 id="report-card-heading">Report card</h2>
      <table>
        <thead><tr><th>Domain</th><th>Grade</th><th>Score</th><th>Notes</th></tr></thead>
        <tbody>{domain_rows}</tbody>
      </table>
    </section>

    <section class="section" aria-labelledby="economy-heading">
      <h2 id="economy-heading">Appendix · Economy</h2>
      <ul>{_list_items(budget_items, "No budget findings.")}</ul>
    </section>

    <section class="section" aria-labelledby="housing-heading">
      <h2 id="housing-heading">Appendix · Housing &amp; labor</h2>
      <ul>{_list_items(housing_items, "Balanced.")}</ul>
    </section>

    <section class="section" aria-labelledby="transit-heading">
      <h2 id="transit-heading">Appendix · Transit</h2>
      <p class="muted">{html.escape(str(transit.get("summary") or ""))}</p>
      <ul>{_list_items(transit_items, "No line detail available.")}</ul>
    </section>

    <footer>CitiesAI read-only civic briefing — not affiliated with Colossal Order.</footer>
  </main>
</body>
</html>"""


def write_report_file(
    snapshot: dict[str, Any],
    meta: SnapshotMeta,
    output: Path,
) -> Path:
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report_html(snapshot, meta), encoding="utf-8")
    return output
