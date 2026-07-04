# Real-life test checklist

Run this after playing a city for 30+ minutes with varied systems (zoning, services, budget, transit).

## Setup

- [ ] `citiesai doctor` passes (export fresh, encyclopedia available)
- [ ] Export age under 11 minutes during test session

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

- [ ] `MISTRAL_API_KEY` set
- [ ] `citiesai ask "..."` returns grounded answer citing snapshot numbers
- [ ] Answer flags stale/partial/unavailable metrics when applicable

## Cursor skill flow

- [ ] Ask 3 my-city questions in Cursor with cities2-advisor skill loaded
- [ ] Agent quotes export metrics before wiki advice
- [ ] Sources line includes wiki URLs + encyclopedia titles

## Tuning notes

Record misfires here (wrong retrieval query, missing metric in brief, etc.) and open an issue or PR.
