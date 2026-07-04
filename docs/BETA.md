# CitiesAI Beta

Thank you for testing CitiesAI. This build is **Windows-only** and **unsigned**. SmartScreen may warn; choose "More info" then "Run anyway" if you trust the source.

## What you need

| Requirement | Notes |
|-------------|--------|
| Windows 10/11 | macOS/Linux not supported in v0.1 |
| Microsoft Edge WebView2 | Usually preinstalled on Windows 11; [install](https://developer.microsoft.com/microsoft-edge/webview2/) if the app window fails to open |
| Cities: Skylines II | Steam or Xbox PC (Game Pass) |
| Internet (optional) | Only for AI answers via your own Mistral key |

You do **not** need Python, Unity, or modding experience. The installer includes the data export mod.

## Install

1. Download `CitiesAI-Setup-0.1.0.exe` from [Releases](https://github.com/XharvaK/CitiesAI/releases) (or the link Doc shared).
2. Run the installer (per-user, no admin).
3. Launch **CitiesAI** from Start Menu. The app opens in its own window (not your browser).
4. Complete the onboarding wizard (or click **Skip setup** if you are already configured):
   - Detect game paths
   - Install data export mod (close CS2 first if it fails)
   - Load a city in-game
   - Optional: paste a free [Mistral](https://console.mistral.ai) API key for AI answers

## Daily use

1. Launch CitiesAI (or leave it running).
2. Play CS2 with **CS2 Data Export** enabled.
3. Dashboard and in-game export both refresh about every 10 seconds.
4. Use **Issues** for setup checks and live city pressures (water, health, jobs, transit).
5. Use **Ask** for grounded advice.
6. Use **Feedback** to report bugs or bad answers.

## AI answers (BYOK)

Stats and dashboard work without any API key. For AI replies:

1. Sign up at [console.mistral.ai](https://console.mistral.ai) (free Experiment tier).
2. Create an API key.
3. Paste in **Settings → AI answers → Save key**.

Your key is stored only in `%APPDATA%\CitiesAI\.env` on your PC.

## Feedback

Use the in-app **Feedback** tab. Submissions go to the beta Discord channel when the maintainer built the installer with a webhook configured. A local copy is always saved under `%APPDATA%\CitiesAI\feedback\`.

Maintainers: [docs/FEEDBACK-DISCORD.md](FEEDBACK-DISCORD.md)

## Known issues (beta)

- **Stale export:** saving a city without loading it does not refresh data; load the city in-game.
- **Mod install fails:** CS2 is probably running; close it and retry.
- **Unsigned installer:** expected until code signing is added.
- **Private repo:** download link may be shared manually until public release.

## Uninstall

Windows Settings → Apps → CitiesAI, or run the uninstaller from Start Menu.

To remove the mod: delete `%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\Mods\CS2DataExport`.

## Developer install (from source)

```powershell
git clone https://github.com/XharvaK/CitiesAI
cd CitiesAI
uv sync --group dev
uv run citiesai setup -y
uv run citiesai gui
```

Mod from source: see [docs/INSTALL-MOD.md](INSTALL-MOD.md).
