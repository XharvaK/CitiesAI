# Changelog

All notable changes to CitiesAI are documented here.

## [0.2.0] — 2026-07-04

### Highlights

This release fixes the dashboard metrics that were misleading or broken since beta: **expense always 0**, **health/wellbeing wrong or n/a on large cities**, and the **traffic card label**. The bundled CS2 Data Export mod is updated to **schema 2.9.0**.

### CS2 Data Export mod (schema 2.9.0)

- **Expense** — now sums all monthly expense categories (loan interest, service upkeep, imports, etc.). Previously only the first category was read, which was almost always zero.
- **Income** — same fix: totals all income sources instead of residential tax only.
- **Wellbeing & health** — exported as **0–100 citizen averages** (matches the in-game happiness panel). Previously exported raw population-weighted sums that CitiesAI misread.

### CitiesAI app

- **Health / wellbeing** — parses both new 2.9.0 exports and older snapshots by dividing weighted sums by resident population. Fixes **n/a** on large cities without requiring everyone to update the mod immediately.
- **Population** — dashboard uses official **resident** count (excludes commuters and tourists).
- **Traffic card** — relabeled **Road / transit ratio** (road vehicles ÷ transit vehicles); shows one decimal. Not a congestion score.
- **Delta display** — fixed red **0** appearing when a metric changed by a fraction (e.g. traffic ratio −0.3).
- **Ask / brief** — technical brief and issue detection use normalized wellbeing/health values.

### Install

Download **`CitiesAI-Setup-0.2.0.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases). After installing, load your city in CS2 so the new export mod can write fresh data.

### Known limitations

- `taxes.*_taxable_income` in the export still reads a single parameter per sector; sector tax breakdowns may be understated.
- Road congestion index is unavailable on current game builds (game API component missing); the Issues tab cannot flag congestion yet.

---

## [0.1.1] — 2026-07-03

- Fix mod install API and packaged app version reporting.
- Discord feedback webhook support.
- Ask panel stale-export caveat.
- Export refresh every 10 seconds.

## [0.1.0] — 2026-06

- Initial beta: dashboard, Issues, Ask (Mistral BYOK), bundled data export mod.
