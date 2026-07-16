# Real-life test checklist

Run after playing a city for 30+ minutes with varied systems (zoning, services, budget, transit).

## Stranger flow (installer beta)

- [ ] Fresh Windows user profile or renamed `%APPDATA%\CitiesAI`
- [ ] Run `CitiesAI-Setup-0.9.1.exe` (or `uv run citiesai gui` from source)
- [ ] Onboarding: detect game → install mod → load city → optional Mistral key
- [ ] Dashboard shows metrics without reading file paths
- [ ] Ask returns streaming answer (or bundle with AI off)
- [ ] Feedback submits (Discord or local fallback)

## Setup

- [ ] `citiesai doctor` passes (export fresh, encyclopedia available)
- [ ] Export age under 30 seconds during test session

## GUI (0.6.x)

- [ ] `citiesai gui` opens a desktop window (pywebview; no browser step)
- [ ] Tabs present: Dashboard, Insights, Issues, Ask, Settings, Feedback
- [ ] Dashboard: metric cards, Fresh/Stale pill, report-card strip → Insights, session digest banner
- [ ] Insights: report card, RCI demand, utilities & services, transit doctor (no Anomalies card)
- [ ] Issues: feed rows open Ask or Settings; push-notifications toggle works
- [ ] Ask: chat streams with LLM key; thumbs up/down on answers
- [ ] Settings: save paths, install/reinstall mod, save/test/replace/remove API key, Updates + mod row at bottom
- [ ] Feedback tab sends report

## CLI questions (with `--no-llm` first)

Ask each; note if brief metrics match in-game UI:

1. What should I prioritize next given my budget?
2. Why is residential demand low / high?
3. Do I need more schools or clinics?
4. Should I add bus lines given current traffic?
5. What is hurting wellbeing or health?
6. Are my industrial zones balanced for workers?
7. Any signs I am losing population?
8. What service coverage gaps should I fix first?

## LLM mode (optional)

- [ ] Mistral key in Settings or `MISTRAL_API_KEY`
- [ ] `citiesai ask "..."` or GUI Ask returns grounded answer citing snapshot numbers
- [ ] Answer flags stale/partial/unavailable metrics when applicable

## Cursor skill flow

- [ ] Ask 3 my-city questions in Cursor with cities2-advisor skill loaded
- [ ] Agent quotes export metrics before wiki advice
- [ ] Sources line includes wiki URLs + encyclopedia titles

## Tuning notes

Record misfires here (wrong retrieval query, missing metric in brief, etc.) and open an issue or PR.
