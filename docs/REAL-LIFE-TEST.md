# Real-life test checklist

Run after playing a city for 30+ minutes with varied systems (zoning, services, budget, transit).

## Stranger flow (installer beta)

- [ ] Fresh Windows user profile or renamed `%APPDATA%\CitiesAI`
- [ ] Run `CitiesAI-Setup-0.1.0.exe` (or `uv run citiesai gui` from source)
- [ ] Onboarding: detect game → install mod → load city → optional Mistral key
- [ ] Dashboard shows metrics without reading file paths
- [ ] Ask returns streaming answer (or bundle with AI off)
- [ ] Feedback submits (Discord or local fallback)

## Setup

- [ ] `citiesai doctor` passes (export fresh, encyclopedia available)
- [ ] Export age under 30 seconds during test session

## GUI (v0.1)

- [ ] `citiesai gui` opens at http://127.0.0.1:8765
- [ ] Dashboard hero + metric cards + freshness pill
- [ ] Health strip in sidebar reflects issues
- [ ] Ask chat streams tokens with LLM key
- [ ] Settings: save paths, install mod, save/test API key
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
