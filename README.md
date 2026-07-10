# CitiesAI

**CitiesAI** is a read-only advisor for **Cities: Skylines II**. It reads your live city stats, searches the official wiki and in-game encyclopedia locally, and (optionally) uses **your own** API key to turn that context into plain-language answers.

## What it does

| Feature | Needs AI key? |
|---------|----------------|
| **Dashboard** — live metrics, session digest, report-card strip | No |
| **Insights** — letter grades, RCI demand, housing & labor, utilities, transit advisor | No |
| **Issues** — setup checks + city pressures; evidence-first advisor inspector | No |
| **Push notifications** — Windows toasts for new/changed issues (Settings → Notifications; off by default) | No |
| **Co-Mayor** — in-game signal strip: compact → evidence advisor → follow-up Ask | Optional for Ask |
| **Auto-updater** — check GitHub Releases from Settings | No |
| Wiki + encyclopedia search | No |
| **Advisor** — grounded advice about *your* city (Civic / Conversational / Analyst styles) | Yes (Mistral, free tier works) |

```text
CS2 (Data Export mod)  →  latest.json  →  CitiesAI dashboard / Ask
Cities2-MCP corpus     →  wiki + encyclopedia  →  retrieval for answers
Your Mistral API key   →  optional LLM  →  synthesized reply
```

Export refreshes about every **5 seconds** while a city is loaded in-game (requires the bundled export mod). When CS2 is closed, the last snapshot stays on disk; the dashboard shows **Stale** after ~15 seconds without a new export — that is normal, not a setup error.

The **Issues** view lists setup problems and **current city pressures** (water, health, jobs, transit, budget, and more) in a ranked queue. Selecting a row opens an evidence-first advisor inspector (evidence → likely causes → actions → optional follow-up Ask). Setup issues can jump to **Settings**. Enable **Push notifications** under **Settings → Notifications** for Windows toasts when issues change (`citiesai gui --watch` enables the same background alerts; the preference persists across sessions and defaults to off).

Choose an **advisor style** during onboarding or in **Settings → Advisor style**:
- **Civic** (default) — concise municipal guidance
- **Conversational** — warmer, game-native co-mayor voice
- **Analyst** — more metrics and reasoning depth

Styles change tone and suggestions only — never measurements, severity, or ranking.

## What you need

| Requirement | Notes |
|-------------|--------|
| **Windows 10/11** | Desktop app (WebView2; usually preinstalled on Win 11) - current release **0.8.2** |
| **Cities: Skylines II** | Steam or Xbox PC (Game Pass) |
| **CS2 Data Export mod** | Bundled in the Windows installer |
| **Mistral API key** | Optional; free Experiment tier is enough for testing |

---

## Install (Windows — recommended)

See [CHANGELOG.md](CHANGELOG.md) for 0.8.2 release notes.

1. Download **`CitiesAI-Setup-0.8.2.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).
2. Run the installer (per-user, no admin). SmartScreen may warn on unsigned builds — use **More info → Run anyway** if you trust the source.
3. Launch **CitiesAI** from the Start menu.
4. Follow the onboarding wizard:
   - **Welcome** — pick Civic / Conversational / Analyst advisor style
   - **Detect / install** — finds your CS2 install and installs CS2 Data Export (close CS2 first if install fails)
   - **Load a city** in-game with the mod enabled; wait ~1 minute for the first export
   - **API key** — optional; skip if you only want the dashboard for now
   Escape dismisses onboarding for the session; Skip/Finish marks it complete.

Beta details: [docs/BETA.md](docs/BETA.md) · Problems: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

---

## Install (from source)

For contributors or anyone who prefers `uv`:

```powershell
git clone https://github.com/XharvaK/CitiesAI
cd CitiesAI
uv sync
uv run citiesai setup -y
uv run citiesai doctor
uv run citiesai gui
```

One-liner without cloning:

```powershell
uvx --from git+https://github.com/XharvaK/CitiesAI citiesai setup -y
```

Mod from source: [docs/INSTALL-MOD.md](docs/INSTALL-MOD.md)

---

## Daily use

1. Launch **CitiesAI** (or leave it open).
2. Play CS2 with **CS2 Data Export** enabled and your city loaded.
3. Check the **Dashboard** for the 12 metric cards, Fresh/Stale pill, and report-card strip.
4. Keep **Co-Mayor** enabled for an always-on signal strip over the game (grade + top issues). Tap an issue for an evidence-first advisor brief, then Ask follow-up or **Back to game**.
5. Open **Insights** for report-card, budget, housing, utilities, and transit analysis.
6. Open **Issues** when something looks wrong — select a row for the advisor inspector, or open **Settings** for setup items.
7. Open **Advisor** and type a question (e.g. *"Why is my budget negative?"*).
8. Use **Feedback** to report bugs or bad answers.

Primary navigation is Dashboard, Insights, Issues, and Advisor. Settings, Feedback, and Diagnostics live as icons in the lower-left rail.

Settings → **Updates** checks GitHub for new installers on startup (Windows packaged builds).

PowerShell helper (repo):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\advisor.ps1 ask "how do I grow residential demand?"
```

---

## Mistral API key walkthrough

CitiesAI uses a **bring-your-own-key** model: your key stays on your PC, and only **you** call Mistral’s API. Dashboard and stats never require a key.

### 1. Create a Mistral account

1. Open **[console.mistral.ai](https://console.mistral.ai)** in your browser.
2. Sign up (email or Google) or log in.
3. Complete **phone (SMS) verification** if prompted — this unlocks the free **Experiment** tier. A credit card is **not** required for basic experimentation.

### 2. Create an API key

1. In the Mistral console (, open your **workspace** (default workspace is fine).
2. Go to **API keys** (sidebar or **Settings → API keys**). or: https://console.mistral.ai/home?profile_dialog=api-keys
3. Click **Create new key** (or **Generate**).
4. Name it something like `CitiesAI` so you can revoke it later.
5. **Copy the key immediately** — Mistral usually shows the full secret only once. It looks like a long random string (not your login password).

If you lose the key, delete the old one in the console and create a new key.

### 3. Add the key to CitiesAI

**Option A — GUI (installer / `citiesai gui`)**

1. Open CitiesAI → **Settings**.
2. Under **AI answers**, paste the key into **API key**.
3. Click **Save key**, then **Test key**. You should see a success message.
4. After save, the key is hidden — use **Replace key** or **Remove key** to change it later.
5. Open **Ask** and try a short question.

The key is stored locally in:

```text
%APPDATA%\CitiesAI\.env
```

**Option B — environment variable (CLI, scripts, or advanced users)**

Current PowerShell session only:

```powershell
$env:MISTRAL_API_KEY = "paste-your-key-here"
citiesai ask "what should I fix first?"
```

Persistent for your Windows user (new terminals after restart):

```powershell
[System.Environment]::SetEnvironmentVariable("MISTRAL_API_KEY", "paste-your-key-here", "User")
```

Restart CitiesAI or open a new terminal after setting a user-level variable.

### 4. Defaults and limits

| Setting | Default |
|---------|---------|
| Provider | Mistral |
| Model | `mistral-medium-latest` |
| Config file | `%APPDATA%\CitiesAI\config.toml` |

Free-tier rate limits apply on Mistral’s side. If Ask fails, check **Settings → Test key** and [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md). Use `citiesai ask "..." --no-llm` to print the context bundle without calling the API.

**Security:** Do not commit or share your API key. Revoke keys you no longer use in the Mistral console.

---

## Commands

| Command | Purpose |
|---------|---------|
| `citiesai gui` | Desktop app: **Dashboard**, **Insights**, **Issues**, **Advisor**, **Settings**, **Feedback**. Close (X) minimizes to the system tray; right-click the tray icon to reopen or exit. |
| `citiesai gui --watch` | GUI + Windows push notifications for city pressures (same as Settings → Notifications; preference persists) |
| `citiesai setup` | Detect game paths and write config |
| `citiesai doctor` | Verify snapshot, wiki, encyclopedia, API key |
| `citiesai context` | Compact city brief from `latest.json` |
| `citiesai retrieve -q "..."` | Wiki + encyclopedia search only |
| `citiesai ask "..."` | Brief + retrieval + LLM answer (if key set) |
| `citiesai ask "..." --no-llm` | Context bundle only (for Cursor/agents) |
| `citiesai history` | Historian metric series for the current city |
| `citiesai diff <before> <after>` | Compare two snapshot files |
| `citiesai transit` | Transit line doctor report |
| `citiesai brief` | Mayor's briefing — session digest, priorities, resolved issues |
| `citiesai report` | Letter-grade report card (CLI) |
| `citiesai mcp` | MCP server for agents (`get_city_brief`, `get_history`, …) |

Important paths:

```text
City snapshot  %USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\ModsData\CS2DataExport\latest.json
Config         %APPDATA%\CitiesAI\config.toml
API key file   %APPDATA%\CitiesAI\.env
Historian DB   %APPDATA%\CitiesAI\historian.db
HTML reports   %APPDATA%\CitiesAI\reports\
```

MCP setup: [docs/CITIESAI-MCP.md](docs/CITIESAI-MCP.md) · Agent workflow: [docs/AGENTS-AND-MCP.md](docs/AGENTS-AND-MCP.md)

---

## Cursor / MCP users

CitiesAI complements agent workflows; it does not replace them.

- Configure [Cities2-MCP](docs/AGENTS-AND-MCP.md) in `~/.cursor/mcp.json` and optionally `citiesai mcp` for live city tools — see [docs/CITIESAI-MCP.md](docs/CITIESAI-MCP.md).
- Copy [skills/cities2-advisor/SKILL.md](skills/cities2-advisor/SKILL.md) into your agent skills folder.
- Run `citiesai ask --no-llm` to get a grounded prompt bundle for your agent.

---

## How the stack fits together

| Layer | Source |
|-------|--------|
| City metrics | [CS2 Data Export](https://github.com/mayor-modder/Cities2-DataExport) mod → `latest.json` |
| Wiki + encyclopedia | [Cities2-MCP](https://github.com/mayor-modder/Cities2-MCP) corpus + `Locale.cok` |
| Optional LLM | Mistral (default), or any OpenAI-compatible endpoint via config |

---

## Development

```powershell
uv sync --group dev
uv run pytest
uv run ruff check citiesai tests
```

Release build (exe + installer):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT — see [LICENSE](LICENSE). CS2 Data Export is a separate MIT project (vendored as a submodule).
