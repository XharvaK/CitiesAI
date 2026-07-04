# CitiesAI — agent notes

Read-only CS2 advisor: city export JSON + Cities2-MCP wiki/encyclopedia + optional Mistral LLM.

## Paths

- Export: `%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\ModsData\CS2DataExport\latest.json`
- Config: `%APPDATA%\CitiesAI\config.toml`

## Workflow (my-city questions)

1. `citiesai doctor` or `scripts/verify-export.ps1`
2. `citiesai context -q "..."` or read `latest.json`
3. Cities2-MCP `search` + `search_encyclopedia` (or `citiesai retrieve`)
4. Synthesize with city numbers first; cite sources

Skill: `skills/cities2-advisor/SKILL.md`

## Workflow (general mechanics)

Use Cities2-MCP + `cities2-knowledge` skill (wiki/encyclopedia only, no city export).

## Mod build (maintainers)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-data-export.ps1
```

Vendor: `vendor/Cities2-DataExport` (git submodule).
