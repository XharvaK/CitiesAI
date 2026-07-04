# Troubleshooting

## Export not found

1. Confirm mod DLL exists:
   `%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\Mods\CS2DataExport\CS2DataExport.dll`
2. Load a **city** (not main menu).
3. Check log:
   `%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\Logs\CS2DataExport.log`
4. Wait up to 10 minutes for first export.

`Modding.log` may show `Enabled Mods: (none)` for local code mods — look for `Loaded CS2DataExport` instead.

## Game Encyclopedia unavailable

`citiesai doctor` reports encyclopedia missing when `Locale.cok` cannot be found.

Set paths explicitly:

```powershell
citiesai setup
# or
$env:CITIES2_GAME_DIR = "C:\path\to\Content"   # folder containing Cities2_Data
$env:CITIES2_LOCALE_COK = "C:\path\to\Locale.cok"
```

### Game Pass (Xbox app)

Game content is often under:

```
C:\XboxGames\<guid>\Content
```

CitiesAI auto-detects `C:\XboxGames\*\Content` with a valid `Locale.cok`.

### Steam

CitiesAI uses Cities2-MCP Steam library discovery. Typical path:

```
<SteamLibrary>\steamapps\common\Cities Skylines II
```

## Unity / modding toolchain hangs (Game Pass)

If in-game `Options → Modding` hangs installing Unity to `Program Files`:

1. Install Unity **2022.3.62f2** via Unity Hub to a user-writable path.
2. Junction Hub editor to the path CS2 expects (see upstream modding docs).
3. **UI Mod Project Template "Outdated"** can be ignored for C#-only mods.

## LLM errors

| Symptom | Fix |
|---------|-----|
| `No LLM API key` | Set `MISTRAL_API_KEY` or use `--no-llm` |
| Rate limit | Mistral free tier is low RPS; wait and retry |
| Wrong model | Set `CITIESAI_LLM_MODEL` or edit config `[llm] model` |

Other providers: set `CITIESAI_LLM_BASE_URL` and `CITIESAI_LLM_API_KEY_ENV`.

## Stale snapshot

Export refreshes every ~10 minutes. If `citiesai context` shows `stale (>11 min)`, save/reload city or wait for next cycle before budget/traffic advice.
