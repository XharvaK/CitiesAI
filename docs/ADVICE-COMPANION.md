# In-game advice companion (experimental)

CitiesAI can write `advice.json` next to your city export for a future in-game overlay.

## Path

`%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\ModsData\CS2DataExport\advice.json`

## Generate from CLI

```powershell
citiesai ask "How do I fix water pressure?" --write-advice
```

## Schema (v1.0.0)

```json
{
  "schema_version": "1.0.0",
  "generated_at_utc": "2026-07-05T12:00:00.0000000Z",
  "title": "Short question summary",
  "body": "Advisor answer text (markdown-friendly plain text)",
  "priority": "normal"
}
```

## Mod integration (planned)

The CS2 Data Export mod may read this file and show a non-blocking in-game toast or panel.
Until then, use the CitiesAI GUI **Insights** tab or `citiesai report --format html`.
