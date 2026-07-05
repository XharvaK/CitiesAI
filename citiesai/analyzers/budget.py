"""Budget analyzer — income, expense, and tax breakdown."""

from __future__ import annotations

from typing import Any

from ..snapshot import pick, pick_group


def _num(value: Any) -> float | int | None:
    if isinstance(value, (int, float)):
        return value
    return None


def analyze_budget(snapshot: dict[str, Any]) -> dict[str, Any]:
    official = pick_group(snapshot, "OfficialCityStatistics")
    finance = pick_group(official, "Finance")
    taxes = pick_group(official, "Taxes")
    services = pick_group(official, "CityServices")

    money = _num(pick(finance, "Money", "money"))
    income = _num(pick(finance, "Income", "income"))
    expense = _num(pick(finance, "Expense", "expense"))
    trade = _num(pick(finance, "Trade", "trade"))

    tax_sectors: list[dict[str, Any]] = []
    sector_keys = [
        ("residential_taxable_income", "Residential"),
        ("commercial_taxable_income", "Commercial"),
        ("industrial_taxable_income", "Industrial"),
        ("office_taxable_income", "Office"),
    ]
    total_taxable = 0.0
    for key, label in sector_keys:
        value = _num(pick(taxes, key))
        if value is not None and value > 0:
            total_taxable += value
            tax_sectors.append({"sector": label, "taxable_income": value})

    for row in tax_sectors:
        if total_taxable > 0:
            row["share_percent"] = round(row["taxable_income"] * 100.0 / total_taxable, 1)

    findings: list[dict[str, str]] = []
    if income is not None and expense is not None:
        net = income - expense
        if net < 0:
            findings.append(
                {
                    "id": "deficit",
                    "severity": "warn",
                    "title": "Monthly deficit",
                    "detail": f"Expenses {expense:,.0f} exceed income {income:,.0f} by {abs(net):,.0f}/month.",
                    "action": "Raise taxes, cut service budgets, or grow taxable base.",
                }
            )
        elif expense > 0 and income / expense < 1.05:
            findings.append(
                {
                    "id": "tight_budget",
                    "severity": "info",
                    "title": "Tight budget margin",
                    "detail": f"Only {net:,.0f}/month surplus ({income / expense * 100:.0f}% coverage).",
                    "action": "Build reserves before major expansions.",
                }
            )

    if money is not None and expense is not None and expense > 0:
        months_runway = money / expense
        if months_runway < 3:
            findings.append(
                {
                    "id": "low_reserves",
                    "severity": "warn",
                    "title": "Low treasury reserves",
                    "detail": f"Treasury covers ~{months_runway:.1f} months of expenses.",
                    "action": "Pause spending or increase income before big projects.",
                }
            )

    service_rows: list[dict[str, Any]] = []
    if isinstance(services, dict):
        for key, value in services.items():
            if key.lower() in ("status", "notes", "source_component"):
                continue
            num = _num(value)
            if num is not None:
                service_rows.append({"service": key.replace("_", " ").title(), "value": num})

    return {
        "treasury": money,
        "income": income,
        "expense": expense,
        "trade": trade,
        "net_monthly": (income - expense) if income is not None and expense is not None else None,
        "tax_sectors": tax_sectors,
        "service_stats": service_rows[:12],
        "findings": findings,
        "summary": (
            f"Net {income - expense:+,.0f}/month; treasury {money:,.0f}."
            if money is not None and income is not None and expense is not None
            else "Budget data partially available."
        ),
    }
