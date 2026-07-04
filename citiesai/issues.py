from __future__ import annotations

from typing import Any, Literal

IssueSeverity = Literal["error", "warn", "info"]

_PATH_LABELS = {
    "game_dir": "Game folder",
    "locale_cok": "Locale file",
    "export_path": "Export file",
}

_SIGNAL_COPY: dict[str, dict[str, str]] = {
    "housing": {
        "title": "Housing pressure detected",
        "detail": "Residential demand or homelessness signals need attention.",
        "ask_prompt": "What should I do about housing pressure in my city?",
    },
    "labor": {
        "title": "Labor market pressure",
        "detail": "Jobs, education, or workforce balance may be off.",
        "ask_prompt": "How can I improve jobs and employment in my city?",
    },
    "mobility": {
        "title": "Limited mobility data",
        "detail": "Traffic and road usage metrics are partial or incomplete.",
        "ask_prompt": "How can I improve traffic and road flow in my city?",
    },
    "economy": {
        "title": "Economy data is partial",
        "detail": "Citizen wealth metrics are estimated from limited household data.",
        "ask_prompt": "What should I prioritize to strengthen my city's economy?",
    },
    "transit": {
        "title": "Transit coverage unclear",
        "detail": "No transit line records were exported, so bus and rail advice is limited.",
        "ask_prompt": "Should I add public transit lines given my current traffic?",
    },
    "budget": {
        "title": "Budget deficit",
        "detail": "City expenses exceed income.",
        "ask_prompt": "What should I fix in my budget to stop running a deficit?",
    },
}


def _issue(
    issue_id: str,
    *,
    severity: IssueSeverity,
    title: str,
    detail: str,
    hint: str = "",
    ask_prompt: str = "",
    report_category: str = "general",
    action_view: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": issue_id,
        "severity": severity,
        "title": title,
        "detail": detail,
        "hint": hint,
        "report_category": report_category,
    }
    if ask_prompt:
        entry["ask_prompt"] = ask_prompt
    if action_view:
        entry["action_view"] = action_view
    return entry


def collect_issues(
    status: dict[str, Any],
    metrics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    for key, entry in (status.get("paths") or {}).items():
        if entry.get("ok"):
            continue
        label = _PATH_LABELS.get(key, key)
        error = entry.get("error", "missing")
        if error == "path does not exist":
            issues.append(
                _issue(
                    f"path_{key}",
                    severity="error",
                    title=f"{label} not found",
                    detail=entry.get("path") or f"Configured {label.lower()} is missing.",
                    hint="Use Settings to re-detect paths or set them manually.",
                    report_category="bug",
                    action_view="settings",
                )
            )
        else:
            issues.append(
                _issue(
                    f"path_{key}",
                    severity="error",
                    title=f"{label} not configured",
                    detail=f"No {label.lower()} is set yet.",
                    hint="Use Settings to detect your game installation.",
                    report_category="bug",
                    action_view="settings",
                )
            )

    if not status.get("mod_installed"):
        issues.append(
            _issue(
                "mod_missing",
                severity="warn",
                title="Data export mod not installed",
                detail="CitiesAI needs the CS2 Data Export mod to read your city.",
                hint="Close CS2, then install the mod from Settings.",
                report_category="bug",
                action_view="settings",
            )
        )

    export = status.get("export")
    if export is None:
        issues.append(
            _issue(
                "export_missing",
                severity="warn",
                title="No city export yet",
                detail="Load a city in CS2 with the Data Export mod enabled.",
                hint="After loading, wait about one minute for the first snapshot.",
                ask_prompt="Why is my city export missing and how do I fix it?",
                report_category="bug",
            )
        )
    elif export.get("stale"):
        age = export.get("age_seconds")
        age_text = f"{int(age)} seconds" if isinstance(age, (int, float)) else "a while"
        issues.append(
            _issue(
                "export_stale",
                severity="warn",
                title="City export is stale",
                detail=f"Last snapshot was received {age_text} ago.",
                hint="Load your city in CS2 and keep the game running.",
                ask_prompt="Why is my city data stale and how do I refresh it?",
                report_category="bug",
            )
        )

    knowledge = status.get("knowledge") or {}
    enc = knowledge.get("encyclopedia") or {}
    if knowledge.get("error"):
        issues.append(
            _issue(
                "knowledge_error",
                severity="error",
                title="Knowledge sources unavailable",
                detail=str(knowledge["error"]),
                hint="Reinstall CitiesAI or report this in Feedback.",
                report_category="bug",
            )
        )
    elif not enc.get("available"):
        issues.append(
            _issue(
                "encyclopedia_missing",
                severity="warn",
                title="Game encyclopedia unavailable",
                detail="Wiki-style answers may be limited until encyclopedia data loads.",
                hint="Check that your game Locale.cok path is correct in Settings.",
                report_category="bug",
                action_view="settings",
            )
        )

    llm = status.get("llm") or {}
    if not llm.get("configured"):
        issues.append(
            _issue(
                "llm_optional",
                severity="info",
                title="AI answers not configured",
                detail="Dashboard stats work without an API key.",
                hint="Add a free Mistral key in Settings for grounded answers.",
                action_view="settings",
            )
        )

    for signal in (metrics or {}).get("signals") or []:
        signal_id = str(signal.get("id", ""))
        copy = _SIGNAL_COPY.get(signal_id)
        if not copy:
            continue
        issues.append(
            _issue(
                f"signal_{signal_id}",
                severity="warn" if signal_id == "budget" else "info",
                title=copy["title"],
                detail=copy["detail"],
                hint=str(signal.get("note", ""))[:240],
                ask_prompt=copy["ask_prompt"],
                report_category="wrong-answer" if signal_id != "budget" else "general",
            )
        )

    return issues


def blocking_issue_count(issues: list[dict[str, Any]]) -> int:
    return sum(1 for issue in issues if issue.get("severity") in ("error", "warn"))
