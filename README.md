# CitiesAI

Read-only AI gameplay advisor for **Cities: Skylines II**.

Combines your live city export (`latest.json` from [CS2 Data Export](https://github.com/mayor-modder/Cities2-DataExport)) with local wiki + in-game encyclopedia search ([Cities2-MCP](https://github.com/mayor-modder/Cities2-MCP)). Optional **Mistral** (or any OpenAI-compatible API) turns retrieval into a direct answer — no Cursor required.

## Quick start

### 1. Install the data export mod

See [docs/INSTALL-MOD.md](docs/INSTALL-MOD.md). Load a city in-game and confirm `latest.json` exists.

### 2. Install CitiesAI

```powershell
# from this repo
uv sync
uv run citiesai setup -y
uv run citiesai doctor
```

Or install without cloning:

```powershell
uvx --from git+https://github.com/XharvaK/CitiesAI citiesai setup -y
```

### 3. Optional: Mistral API key (free tier)

1. Sign up at [console.mistral.ai](https://console.mistral.ai) (SMS verification, no credit card for Experiment tier).
2. Create an API key.
3. Set environment variable:

```powershell
$env:MISTRAL_API_KEY = "your-key-here"
```

### 4. Ask a question

```powershell
citiesai ask "what should I build first?"
citiesai ask "why is my budget negative?" --no-llm   # bundle only, for Cursor/agents
```

PowerShell wrapper (repo):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\advisor.ps1 ask "how do I grow residential demand?"
```

## Commands

| Command | Purpose |
|---------|---------|
| `citiesai setup` | Detect game paths, write config |
| `citiesai doctor` | Verify export, wiki, encyclopedia |
| `citiesai context` | Compact city brief from `latest.json` |
| `citiesai retrieve -q "..."` | Wiki + encyclopedia search only |
| `citiesai ask "..."` | Brief + retrieval + LLM answer (if key set) |

Config file: `%APPDATA%\CitiesAI\config.toml` (Windows) or `~/.config/citiesai/config.toml`.

## Cursor / MCP users

- Configure [Cities2-MCP](docs/AGENTS-AND-MCP.md) in `~/.cursor/mcp.json`.
- Copy [skills/cities2-advisor/SKILL.md](skills/cities2-advisor/SKILL.md) to your agent skills folder.
- Use `citiesai ask --no-llm` to get a grounded prompt bundle for your agent.

## Stack

| Layer | Source |
|-------|--------|
| City metrics | CS2 Data Export mod → `latest.json` |
| Wiki + encyclopedia | `cities2-mcp` (bundled corpus + `Locale.cok`) |
| Optional LLM | Mistral (default), or OpenAI-compatible endpoint |

## Development

```powershell
uv sync --group dev
uv run pytest
uv run ruff check citiesai tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE). CS2 Data Export is a separate MIT project (vendored as submodule).
