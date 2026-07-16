# Install CS2 Data Export mod

CitiesAI needs [CS2 Data Export](https://github.com/mayor-modder/Cities2-DataExport) to write `latest.json` while you play.

## Expected output

```
%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\ModsData\CS2DataExport\latest.json
```

Default export interval: **10 seconds** after city load.

Override with environment variable `CS2DATAEXPORT_INTERVAL_SECONDS` (minimum 5).

Default transit capture cooldown: **10 minutes** (`CS2DATAEXPORT_TRANSIT_CAPTURE_COOLDOWN_MINUTES`). Snapshot retention default: **500**.

## Option A: Paradox Mods (when published)

1. Open Cities: Skylines II → Mods → Browse.
2. Search for **CS2 Data Export** by mayor-modder.
3. Subscribe and enable.
4. Load a city.

Local code mods in `%USERPROFILE%\AppData\LocalLow\Colossal Order\Cities Skylines II\Mods\CS2DataExport\` also auto-load without appearing in Library.

## Option B: Build from source (Windows)

### Prerequisites

- Cities: Skylines II with modding toolchain installed (`Options → Modding` in-game).
- .NET SDK (game toolchain provides build tools).

### Automated (this repo)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-data-export.ps1
```

### Manual

See upstream [INSTALL.md](https://github.com/mayor-modder/Cities2-DataExport/blob/main/INSTALL.md).

## Verify

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify-export.ps1
# or
citiesai doctor
```

Load a city, wait up to one export cycle, then re-run verify.
