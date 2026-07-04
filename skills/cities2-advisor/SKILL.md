---
name: cities2-advisor
description: "Use for Cities: Skylines II questions about the player's current city. Combines live CS2 Data Export snapshot (latest.json) with Cities2-MCP wiki and Game Encyclopedia retrieval."
metadata:
  short-description: "CS2 my-city advisor with live export"
---

# Cities2 Advisor (my city)

Use when the user asks about **their current CS2 city**: budget, demand, traffic, services, growth, or what to fix next. For generic mechanics only, use `cities2-knowledge`.

## Inputs

1. **City snapshot:** `%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\ModsData\CS2DataExport\latest.json`
2. **Knowledge:** Cities2-MCP (`search`, `search_encyclopedia`, `get_page`, `get_encyclopedia_entry`)

CLI alternative:

```powershell
citiesai context -q "question"
citiesai ask "question" --no-llm
```

## Workflow

1. Confirm export exists (`citiesai doctor`). If missing, user must load a city with CS2 Data Export installed.
2. Read snapshot or run `citiesai context -q "..."`. Note `ExportedAtUtc`. Stale if older than ~90 seconds.
3. Ground advice in city metrics first (treasury, income/expense, population, wellbeing, crime, congestion, transit).
4. Retrieve knowledge via Cities2-MCP with compact keyword queries (4–10 terms), derived from question + snapshot signals.
5. Synthesize one actionable answer with sources.

## Answer style

- Lead with snapshot evidence.
- Do not invent null/unavailable metrics.
- Flag conflicts (e.g. subway question but zero transit lines).
- End with wiki URLs + encyclopedia entry titles.

## Do not

- Suggest cheats or save editing.
- Browse the live web unless asked.
- Treat wiki guides as hard mechanics without encyclopedia support.
