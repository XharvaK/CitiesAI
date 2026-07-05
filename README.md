# CitiesAI

**CitiesAI** is a read-only advisor for **Cities: Skylines II**. It reads your live city stats, searches the official wiki and in-game encyclopedia locally, and (optionally) uses **your own** API key to turn that context into plain-language answers.

No Cursor, no cloud account for CitiesAI itself, and no changes to your save — the app only reads export data while you play.

## What it does

| Feature | Needs AI key? |
|---------|----------------|
| Dashboard (population, budget, transit, signals) | No |
| Issues & setup checks | No |
| Wiki + encyclopedia search | No |
| **Ask** — grounded advice about *your* city | Yes (Mistral, free tier works) |

```text
CS2 (Data Export mod)  →  latest.json  →  CitiesAI dashboard / Ask
Cities2-MCP corpus     →  wiki + encyclopedia  →  retrieval for answers
Your Mistral API key   →  optional LLM  →  synthesized reply
```

Export refreshes about every **5 seconds** while a city is loaded in-game (requires the bundled export mod). When CS2 is closed, the last snapshot stays on disk; the dashboard shows **Stale** after ~15 seconds without a new export — that is normal, not a setup error.

The **Issues** tab lists setup problems and **current city pressures** (water, health, jobs, transit, budget, and more) with one-click **Ask about this** prompts.

## What you need

| Requirement | Notes |
|-------------|--------|
| **Windows 10/11** | v0.5.2 ships as a desktop app (WebView2; usually preinstalled on Win 11) |
| **Cities: Skylines II** | Steam or Xbox PC (Game Pass) |
| **CS2 Data Export mod** | Bundled in the Windows installer, or install manually — see [docs/INSTALL-MOD.md](docs/INSTALL-MOD.md) |
| **Mistral API key** | Optional; free Experiment tier is enough for testing |

---

## Install (Windows — recommended)

1. Download **`CitiesAI-Setup-0.5.2.exe`** from [Releases](https://github.com/XharvaK/CitiesAI/releases).
2. Run the installer (per-user, no admin). SmartScreen may warn on unsigned builds — use **More info → Run anyway** if you trust the source.
3. Launch **CitiesAI** from the Start menu.
4. Follow the onboarding wizard:
   - **Detect paths** — finds your CS2 install and `Locale.cok`
   - **Install mod** — copies CS2 Data Export (close CS2 first if install fails)
   - **Load a city** in-game with the mod enabled; wait ~1 minute for the first export
   - **API key** — optional; skip if you only want the dashboard for now

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
3. Check the **Dashboard** for live metrics and the Fresh/Stale pill.
4. Open **Ask** and type a question (e.g. *"Why is my budget negative?"*).
5. Use **Feedback** to report bugs or bad answers.

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
4. Open **Ask** and try a short question.

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
| `citiesai gui` | Desktop app: **Dashboard**, **Insights**, **Issues**, **Ask**, **Settings**, **Feedback** |
| `citiesai gui --watch` | GUI + desktop notification alerts for city pressures |
| `citiesai setup` | Detect game paths and write config |
| `citiesai doctor` | Verify snapshot, wiki, encyclopedia, API key |
| `citiesai context` | Compact city brief from `latest.json` |
| `citiesai retrieve -q "..."` | Wiki + encyclopedia search only |
| `citiesai ask "..."` | Brief + retrieval + LLM answer (if key set) |
| `citiesai ask "..." --no-llm` | Context bundle only (for Cursor/agents) |
| `citiesai history` | Historian metric series for the current city |
| `citiesai diff --before … --after …` | Compare two snapshot files |
| `citiesai transit` | Transit line doctor report |
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
