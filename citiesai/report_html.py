"""Generate shareable HTML city reports."""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .analyzers import analyze_budget, analyze_housing_labor, analyze_transit_lines
from .city_issues import detect_city_issues
from .dashboard import extract_headline_metrics
from .report_ops import build_and_persist_report_card
from .snapshot import SnapshotMeta


def render_report_html(
    snapshot: dict[str, Any],
    meta: SnapshotMeta,
) -> str:
    metrics = extract_headline_metrics(snapshot, meta)
    report = build_and_persist_report_card(snapshot, meta)
    budget = analyze_budget(snapshot)
    housing = analyze_housing_labor(snapshot)
    transit = analyze_transit_lines(snapshot)
    issues = detect_city_issues(snapshot)
    city = html.escape(str(metrics.get("city_name") or "Your city"))
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    domain_rows = ""
    for domain in report["domains"]:
        delta = domain.get("grade_delta")
        delta_html = f' <span class="delta">{html.escape(delta)}</span>' if delta else ""
        domain_rows += f"""
        <tr>
          <td>{html.escape(domain['label'])}</td>
          <td class="grade grade-{html.escape(domain['grade'])}">{html.escape(domain['grade'])}</td>
          <td>{domain['score']:.0f}</td>
          <td class="muted">{html.escape(str(domain.get('detail', '')))}{delta_html}</td>
        </tr>"""

    issue_items = "".join(
        f"<li><strong>{html.escape(str(i.get('title', '')))}</strong> — {html.escape(str(i.get('detail', '')))}</li>"
        for i in issues[:8]
    )
    transit_items = "".join(
        f"<li><strong>{html.escape(group['title'])}</strong> "
        f"({group['line_count']} lines, {html.escape(group['severity'])}): "
        f"{html.escape(group['diagnosis'])}</li>"
        for group in (transit.get("problem_groups") or [])[:6]
    )
    housing_items = "".join(
        f"<li><strong>{html.escape(f['title'])}</strong> — {html.escape(f['detail'])}</li>"
        for f in (housing.get("findings") or [])[:6]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CitiesAI Report — {city}</title>
  <style>
    :root {{ font-family: system-ui, sans-serif; color: #1a1a2e; background: #f4f6fb; }}
    body {{ max-width: 880px; margin: 2rem auto; padding: 0 1rem; }}
    .card {{ background: #fff; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 1rem; box-shadow: 0 2px 12px rgba(0,0,0,.06); }}
    h1 {{ margin: 0 0 .25rem; font-size: 1.6rem; }}
    .overall {{ font-size: 2.5rem; font-weight: 700; }}
    .muted {{ color: #5c6478; font-size: .92rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: .5rem .25rem; border-bottom: 1px solid #e8ebf2; }}
    .grade {{ font-weight: 700; font-size: 1.1rem; }}
    .grade-A {{ color: #0d7a4a; }} .grade-B {{ color: #2d8a3e; }}
    .grade-C {{ color: #b8860b; }} .grade-D {{ color: #c45c26; }} .grade-F {{ color: #b42318; }}
    .delta {{ color: #5c6478; font-size: .85rem; }}
    ul {{ margin: .5rem 0; padding-left: 1.2rem; }}
    footer {{ margin-top: 2rem; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{city}</h1>
    <p class="muted">Generated {generated} · Export {html.escape(str(meta.exported_at_utc or 'n/a'))}</p>
    <p>Overall grade <span class="overall grade grade-{html.escape(report['overall_grade'])}">{html.escape(report['overall_grade'])}</span>
       ({report['overall_score']:.0f}/100)</p>
    <p class="muted">{html.escape(budget.get('summary', ''))}</p>
  </div>
  <div class="card">
    <h2>Report card</h2>
    <table>
      <thead><tr><th>Domain</th><th>Grade</th><th>Score</th><th>Notes</th></tr></thead>
      <tbody>{domain_rows}</tbody>
    </table>
  </div>
  <div class="card">
    <h2>Active issues</h2>
    <ul>{issue_items or '<li class="muted">No major issues detected.</li>'}</ul>
  </div>
  <div class="card">
    <h2>Transit doctor</h2>
    <p class="muted">{html.escape(transit.get('summary', ''))}</p>
    <ul>{transit_items or '<li class="muted">No line detail available.</li>'}</ul>
  </div>
  <div class="card">
    <h2>Housing &amp; labor</h2>
    <ul>{housing_items or '<li class="muted">Balanced.</li>'}</ul>
  </div>
  <footer class="muted">CitiesAI read-only city report — not affiliated with Colossal Order.</footer>
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
