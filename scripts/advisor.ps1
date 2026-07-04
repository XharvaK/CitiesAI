#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$userDataPath = Join-Path $env:USERPROFILE 'AppData\LocalLow\Colossal Order\Cities Skylines II'
$defaultExport = Join-Path $userDataPath 'ModsData\CS2DataExport\latest.json'

if (-not $env:CITIESAI_EXPORT_PATH) {
    $env:CITIESAI_EXPORT_PATH = $defaultExport
}

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [Console]::OutputEncoding

Push-Location $repoRoot
try {
    if ($args.Count -eq 0) {
        uv run citiesai --help
        exit $LASTEXITCODE
    }
    uv run citiesai @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
