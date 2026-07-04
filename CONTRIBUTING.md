# Contributing

Thanks for helping improve CitiesAI.

## Setup

```powershell
git clone https://github.com/XharvaK/CitiesAI.git
cd CitiesAI
git submodule update --init --recursive
uv sync --group dev
```

## Checks

```powershell
uv run ruff check citiesai tests
uv run pytest
```

## Pull requests

- One focused change per PR.
- Add tests for behavior changes in `tests/`.
- Do not commit API keys or `config.toml` with secrets.
- Update docs when CLI or setup flow changes.

## Vendor mod

`vendor/Cities2-DataExport` tracks [mayor-modder/Cities2-DataExport](https://github.com/mayor-modder/Cities2-DataExport). Bump submodule for mod updates; do not fork logic into CitiesAI unless necessary.
