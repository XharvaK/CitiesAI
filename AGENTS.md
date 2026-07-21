# CitiesAI agent notes

Read-only CS2 advisor: city export JSON + Cities2-MCP wiki/encyclopedia + optional Mistral LLM.

## Paths

- Export: `%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\ModsData\CS2DataExport\latest.json`
- Config: `%APPDATA%\CitiesAI\config.toml`

## Workflow (my-city questions)

1. `citiesai doctor` or `scripts/verify-export.ps1` — toolchain only (paths, mod, export parseable, knowledge). `Result: OK` does **not** mean the city is healthy or the export is fresh.
2. Check freshness via `ExportedAtUtc` / `citiesai context` / Issues; city pressures via Insights or Issues (not doctor exit code).
3. `citiesai gui` (dashboard, insights, ask, settings, feedback) or `citiesai context -q "..."` or read `latest.json`
4. `citiesai history --digest` for cross-session changes; `citiesai report` / `citiesai transit` for analyzers
5. Cities2-MCP `search` + `search_encyclopedia` (or `citiesai retrieve`); optional `citiesai mcp` for agent tools
6. Synthesize with city numbers first; cite sources

Skill: `skills/cities2-advisor/SKILL.md`

## Workflow (general mechanics)

Use Cities2-MCP + `cities2-knowledge` skill (wiki/encyclopedia only, no city export).

## Mod build (maintainers)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-data-export.ps1
```

Vendor: `vendor/Cities2-DataExport` (git submodule).

## Cursor Cloud specific instructions

Python 3.11+ project managed by `uv`. Standard commands live in `CONTRIBUTING.md` / `.github/workflows/ci.yml`: `uv sync --group dev`, `uv run ruff check citiesai tests`, `uv run pytest`. The update script already runs `git submodule update --init --recursive` + `uv sync --group dev`.

Non-obvious caveats for this Linux/headless environment:

- Qt/PySide6 needs headless mode. Run the GUI, the Co-Mayor HUD, and `pytest` with `QT_QPA_PLATFORM=offscreen` (no display available). Without it the HUD/GUI code fails with `libEGL.so.1` / xcb errors. The Qt system libs (`libegl1`, `libgl1`, `libxkbcommon0`, etc.) are already installed in the base image.
- Two tests fail on Linux and are expected (they pass on Windows / newer submodule pin): `tests/test_capabilities.py::test_hidden_subprocess_kwargs_on_windows` (Windows-only API) and `tests/test_boundaries_091.py::test_schema_md_matches_runtime_version` (pinned submodule ships SCHEMA `2.11.0`, test expects `2.12.0`). Everything else passes (204 passing).
- The GUI/dashboard reads the city export from the **configured** path only — `~/AppData/LocalLow/Colossal Order/Cities Skylines II/ModsData/CS2DataExport/latest.json` on Linux — and does NOT honor the global `--export` flag. To test offline without CS2, copy `vendor/Cities2-DataExport/sample/latest.sample.json` to that path first. CLI commands (`context`, `report`, `ask`, `doctor`) DO honor `--export PATH`.
- Run the GUI headless: `citiesai gui --no-window --host 127.0.0.1 --port 8765` (REST API at `http://127.0.0.1:8765/`, e.g. `/api/dashboard`, `/api/issues`, `/api/version`). `--browser` opens a browser tab; a native window is Windows-only.
- CS2 is not installed here, so `citiesai doctor` reports setup issues (game folder / locale / mod) — expected. Wiki knowledge, analyzers, dashboard, and offline `ask --no-llm` still work. `Ask`/advisor LLM answers need `MISTRAL_API_KEY` (optional).
