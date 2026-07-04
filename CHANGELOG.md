# Changelog

All notable changes to CitiesAI are documented here.

## [0.3.0] — 2026-07-04

### Export data quality (mod + advisor)

- **Mobility** — cities with no transit lines no longer report false `partial` status (empty line set is `ok`).
- **Transit performance & line detail** — `ok` when the city has no transit lines instead of warning cards.
- **Economy / land value** — reads `Game.Net.LandValue` on each building’s road edge (same path as the in-game land value infoview).
- **City name** — export falls back to `continue_game.json` when ECS city name is empty; dashboard shows **Fabius** (etc.) instead of “Unnamed city”.
- **Issues tab** — export `partial` coverage is no longer surfaced as city problems; use **Diagnostics** for export metadata.

### Dashboard & UI

- Redesigned clickable metric cards with detail graphs and CS2-style hourly badges (`+¢…/h`, `+…/h`).
- **Diagnostics** modal on the dashboard; Settings diagnostics panel removed.
- Treasury / income / expense show **¢** on cards and graphs.
- Removed sidebar subtitle “City advisor for CS2”.

### Ask

- Fixed broken numbered-list rendering in AI answers.

### Install

Download **`CitiesAI-Setup-0.3.0.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases). Close CS2 before installing so the bundled export mod can update.

---

## [0.2.1] — 2026-07-04

### Dashboard

- **Redesigned metric cards** — category accents, hover affordance, clickable for detail graphs.
- **Metric detail modal** — session-history line chart for all eight metrics (including **Employment**, which previously had no graph).
- **Hourly badges** — Treasury shows CS2-style `+¢… /h`; Population shows `+… /h` from official monthly finance and population-flow stats.
- **Diagnostics** — “Technical details & paths” moved to **Settings → City snapshot diagnostics**; **Diagnostics** link on the dashboard hero.

### Ask

- **Numbered lists** — fixed broken `1.` / `2.` / `1.` rendering in AI answers (prompt + markdown renderer).

### Install

Download **`CitiesAI-Setup-0.2.1.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).

---

## [0.2.0] — 2026-07-04

### Highlights

This release fixes the dashboard metrics that were misleading or broken since beta: **expense always 0**, **health/wellbeing wrong or n/a on large cities**, and the **traffic card label**. The bundled CS2 Data Export mod is updated to **schema 2.9.0**.

### CS2 Data Export mod (schema 2.9.0)

- **Expense** — now sums all monthly expense categories (loan interest, service upkeep, imports, etc.). Previously only the first category was read, which was almost always zero.
- **Income** — same fix: totals all income sources instead of residential tax only.
- **Wellbeing & health** — exported as **0–100 citizen averages** (matches the in-game happiness panel). Previously exported raw population-weighted sums that CitiesAI misread.
- **City name** — read from `CityConfigurationSystem.cityName` (dashboard no longer shows "Unnamed city" for named saves).

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
