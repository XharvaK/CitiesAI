# Changelog

All notable changes to CitiesAI are documented here.

## [0.7.2] — 2026-07-06

### Fixes

- **Insights** — report card, analyzers, and overall score trend now refresh every poll while the Insights tab is active (same ~5s cadence as Dashboard).

### Install

Download **`CitiesAI-Setup-0.7.2.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).

---

## [0.7.1] — 2026-07-06

### Fixes

- **System tray** — removed **Compact HUD** from the tray right-click menu (HUD remains available from Settings).
- **Dashboard** — infer water/sewage fulfillment % from capacity vs consumption when the export omits `fulfillment_percent`.
- **CS2 Data Export (vendor)** — restore typed RCI demand probe (fixes `demand_factors_semantics: unavailable`); harden official city statistics against null game date / sample count; fix `EntityQuery` double-dispose; infer utility fulfillment when fulfilled consumption is missing.

### Install

Download **`CitiesAI-Setup-0.7.1.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).

---

## [0.7.0] — 2026-07-06

### Correctness — revive dead wiring

- **Housing/labor analyzer** — reads schema 2.11 field names (`total_households`, `jobs_minus_current_workers`, education-level maps); new tests.
- **City issues** — `CityServices` group fix; moving-away uses monthly flow; per-capita thresholds for homeless/unemployment.
- **Historian** — issue re-open no longer crashes on `UNIQUE`; WAL mode; snapshot retention pruning.
- **CLI** — `--export` honored by `transit`/`brief`/`report`; `--version` flag; doctor stale threshold aligned to 15s.
- **Report card** — transit grade falls back to network summary when line detail export is sparse.

### Security & performance

- **Session token** — mutating GUI API routes require `X-CitiesAI-Token`; token injected into served HTML.
- **Updater** — GitHub host allowlist; SHA256 verification; streamed atomic download to `.partial`.
- **Config/env** — atomic writes for `config.toml` and `.env`; Discord webhook env var validated.
- **Dashboard poll** — single historian sync per request; export/config mtime caching.

### Features

- **Fix This First** — dashboard card ranking top 1–3 session actions.
- **Anomaly Watch** — historian spike detection merged into Issues feed.
- **RCI demand drivers** — negative factor chips per zone in Insights.
- **Ask upgrades** — deduped retrieval, non-agentic multi-turn history, post-run sources SSE, 480s client timeout, cancel/abort on clear.
- **MCP** — `get_transit_lines` tool added.
- **HUD** — lightweight `/api/hud` endpoint; compact overlay with treasury/pop ±/hr, overall grade, top priority, stale dot.

### UI polish (0.7.0)

- **Ask** — removed Cancel button; scrollbar edge-aligned with Insights; Send shows "Sending…" during stream.
- **Feedback** — Send button right-aligned in footer row.
- **RCI demand** — deduped summary/row copy; humanized driver labels (`factor_N` → Demand factor N).
- **Grade badges** — A–F pill badges on dashboard strip and Insights report card.
- **Dashboard** — unified City Briefing card (digest, priorities, resolved, forecasts, grade deltas); metrics section header; 12-card 3×4 grid.
- **Compact HUD v2** — frameless always-on-top strip from Settings; treasury + population ±/hr, grade badge, top priority alert.
- **System tray** — tray icon on launch; closing the window (X) minimizes to tray; right-click **Open** or **Exit** (full quit).
- **Insights** — removed redundant Budget & treasury card (treasury/net already on Dashboard; economy grade on report card).
- **Single instance** — second launch focuses the existing window instead of opening another tray icon.
- **Updater** — when you're on a newer build than GitHub's latest tag, status no longer claims an older release is "latest".

### Mod (CS2 Data Export)

- **Transit access gaps** — passenger trip carrier detection enabled; `EntityQuery` disposal fixes.
- Target schema **2.12** groundwork for deferred coverage fields.

### Install

Download **`CitiesAI-Setup-0.7.0.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).

---

## [0.6.2] — 2026-07-05

### UI polish

- **Ask** — answer feedback uses palette-aligned thumb icons (sage up / amber hover / red down) instead of emoji.
- **Insights** — removed Anomalies card (covered by Issues tab); hide city-services staffing row when export has no data.
- **Issues** — compact feed layout with severity dots; rows open Ask (city pressures) or Settings (setup); removed session-count meta and duplicate in-app Alerts center.
- **Settings** — API key configured-state panel; push notifications toggle redesign; Updates + Data export mod paired at bottom; cleaner version pill in Updates card.
- **Dashboard** — stale age formatting (minutes/hours); removed non-functional Next line advisor card.

### Install

Download **`CitiesAI-Setup-0.6.2.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).

---

## [0.6.1] — 2026-07-05

### Fixes

- **Transit round trip** — export mod corrected tick→in-game-minute conversion (~60× inflation inherited from XTM UI helper); Insights table shows `8h 25m` style labels for long trips.
- **Auto-updater** — GitHub Releases check on startup; Settings → Updates card with download & silent install (Windows packaged builds). Handles API 403/rate limits with release-page fallback and shows “No updates available” when on latest.
- **Dashboard** — hide empty update banner (was showing as a green bar above Mayor's briefing when no update available).
- **Settings** — AI answers card layout aligned and grouped (provider/model row, panel sections, status pill in header).
- **GUI startup** — fix broken `app.js` parse error that left the dashboard stuck on “Checking…”.

### Install

Download **`CitiesAI-Setup-0.6.1.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).

---

## [0.6.0] — 2026-07-05

### Advisor release — dashboard to session coach

- **Next Line Advisor** — uses `transit_access_gap_semantics` hotspots to suggest where the next transit line should go (Insights, Issues, Ask tool, MCP).
- **Issue lifecycle** — tracks city pressures across sessions; Issues tab shows age and recently resolved items; session digest celebrates fixes.
- **Mayor's Briefing** — session-start summary on the dashboard, `citiesai brief` CLI, and MCP `get_mayors_briefing`.
- **Dashboard polish** — 12-metric grid (power/water/sewage row), utilities & services card, sidebar ALERTS, Insights layout; remove anomalies/range/budget redundancy.
- **Small wins** — grade history chart in Insights, in-app Alerts center (watch toasts persisted), Ask answer thumbs up/down feedback.
- **Schema 2.11** — vendored CS2 Data Export adds `demand_factors_semantics` (RCI bars + factor maps) and `utilities_services_semantics` (electricity, garbage); CitiesAI analyzers, Issues, Insights, dashboard Power card, Ask/MCP tools.

---

## [0.5.2] — 2026-07-05

### Fixes

- **Ask agentic loop** — graceful fallback when tool rounds are exhausted; pre-injected retrieval bundle and session history for “drop/decline” questions; configurable `max_tool_rounds` (default 8); **Deep research** toggle in Settings.
- **Workforce brief** — city brief and issue detection now read `workers` / `unemployed` from the export (fixes bogus “0 employed workers” in Ask).

### Install

Download **`CitiesAI-Setup-0.5.2.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).

---

## [0.5.1] — 2026-07-05

### Fixes

- **Economy grade** — surplus cities weighted toward margin (65/35), 12-month runway projection, treasury momentum bonus, and minimum **C/B** floor for healthy margins.
- **Unemployment / congestion** — workforce fallback when education employment rate is missing; historian **metrics schema v2** migration re-ingests snapshots so sparklines populate after upgrading from 0.4/0.5.
- **Sparklines** — show live metric when historian has fewer than two points for a new metric.

### Install

Download **`CitiesAI-Setup-0.5.1.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).

---

## [0.5] — 2026-07-05

### Metrics & export (schema 2.10.0)

- **Unemployment** — dashboard shows unemployment % (derived from employment rate), not employment.
- **Traffic congestion** — replaces road/transit ratio; CS2 Data Export now reads slow `Blocker+Vehicle` entities (`m_MaxSpeed < 6`) with optional bottleneck counts.
- **Economy grade** — surplus cities get projected runway credit; strong treasuries no longer score **D** when monthly margin is healthy.
- **Hourly badges** — session delta hidden under Population/Treasury when `/h` is shown.

### Insights

- **Transit doctor** — recurring line issues grouped by type with collapsed per-line drill-down; fixed diagnosis overwrite bug.

### GUI

- Sidebar **READY** strip text centered.

### Install

Download **`CitiesAI-Setup-0.5.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases). Close CS2 before installing so the bundled export mod (schema **2.10.0**) can update.

---

## [0.4] — 2026-07-05

### Logic & performance

- **Grade deltas** — report card now loads historian history before comparing sessions; deltas work in GUI, CLI, and MCP.
- **Wellbeing scoring** — fixed inflated grades when only wellbeing was present.
- **Historian** — persistent per-city history; sync throttle is lock-safe; watch mode uses historian instead of an in-memory poller.
- **Poll cost** — knowledge cache no longer reloads on every `/api/status`; dashboard bundles issues; status polls every ~60s.
- **History & sync** — dashboard and historian cap raised to **1000 points**; mod export, historian sync, and GUI poll aligned at **5 seconds**; stale threshold **15 seconds**.
- **Watch toasts** — persistent issue notifications re-fire at most every **30 minutes** (was ~5–10 minutes).
- **City switch** — loading another save or new world clears Ask chat, resets LLM conversation by city name, and gives fresh desktop-notification cooldowns per city.

### GUI

- SSE Ask keeps sources visible while tokens stream; chat history XSS fixed.
- Dashboard shows an honest error card instead of infinite skeleton when export is missing.
- Poll error toasts deduplicated; desktop-notifications toggle no longer races with server state.
- Manual **Refresh** button removed (5s auto-poll covers dashboard updates).
- Ask **Sources** collapsed by default; chat auto-scrolls to the latest message.
- Sidebar stays fixed; only the right panel scrolls; status strip shows **READY** (version label removed).
- Rectangular status badges and chips (no pill outlines); improved scrollbar inset and Settings path spacing.

### Security & packaging

- Static path traversal blocked; JSON bodies capped at 1 MB; report export restricted to `%APPDATA%/CitiesAI/reports`.
- Installer version read from `pyproject.toml` at build time; fallback version **0.4**.

### Install

Download **`CitiesAI-Setup-0.4.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases). Close CS2 before installing so the bundled export mod can update.

---

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

---

## [0.1.1] — 2026-07-03

- Fix mod install API and packaged app version reporting.
- Discord feedback webhook support.
- Ask panel stale-export caveat.
- Export refresh every 10 seconds.

## [0.1.0] — 2026-06

- Initial beta: dashboard, Issues, Ask (Mistral BYOK), bundled data export mod.
