# Troubleshooting

## Export not found

1. Confirm mod DLL exists:
   `%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\Mods\CS2DataExport\CS2DataExport.dll`
2. Load a **city** (not main menu).
3. Check log:
   `%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\Logs\CS2DataExport.log`
4. Wait up to 10 seconds for first export.

`Modding.log` may show `Enabled Mods: (none)` for local code mods. Look for `Loaded CS2DataExport` instead.

## Performance / FPS drop with export mod

If enabling CS2 Data Export lowers FPS sharply on a large city:

1. **Update to the latest CitiesAI release** — export cadence, transit capture cooldown, and hot paths were tightened further (see CHANGELOG Performance).
2. **Quick A/B test** — set `CS2DATAEXPORT_TRANSIT_CAPTURE=off` before launching CS2 (system env or Steam launch options). If FPS recovers, the transit access-gap observer was the bottleneck; other metrics still export.
3. **Tune observer** (optional):
   - `CS2DATAEXPORT_INTERVAL_SECONDS` (default **10**, minimum 5)
   - `CS2DATAEXPORT_TRANSIT_OBSERVE_EVERY_N_FRAMES=8` (default 6)
   - `CS2DATAEXPORT_TRANSIT_CAPTURE_COOLDOWN_MINUTES` (default **10**; set `0` for continuous rolling capture)
4. **Profile** — `CS2DATAEXPORT_PROFILE=1` writes per-phase ms to `CS2DataExport.log`.

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
| `Agentic loop exceeded maximum tool rounds` | Complex Ask questions can exhaust tool rounds. CitiesAI should auto-fallback; if you still see this, disable **Deep research** in Settings or run `citiesai ask "..." --no-agentic` |
| Wrong model | Set `CITIESAI_LLM_MODEL` or edit config `[llm] model` |

Other providers: set `CITIESAI_LLM_BASE_URL` and `CITIESAI_LLM_API_KEY_ENV`.

## Stale snapshot

Export refreshes every ~10 seconds. If `citiesai context` shows `stale (>30 sec)`, load the correct city in-game or wait for the next cycle.
