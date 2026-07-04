# Brand assets

Source logo: `logo.png` (square PNG, transparent or dark background).

Generate ICO + sync into the GUI bundle:

```powershell
uv run python scripts\generate-brand-assets.py
```

Outputs:

- `CitiesAI.ico` — Windows exe/installer icon (PyInstaller + Inno Setup)
- `../citiesai/gui/static/logo.png` — sidebar + HTML favicon
- `../citiesai/gui/static/favicon.ico` — legacy favicon fallback

Replace `logo.png` here, then rerun the script before `scripts\build-release.ps1`.
