#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\game-paths.ps1"

if (-not (Test-Path -LiteralPath $LatestExport)) {
    Write-Host "Export not found: $LatestExport" -ForegroundColor Red
    Write-Host 'Load a city in CS2 with CS2 Data Export enabled, then wait up to 10 seconds for an export cycle.'
    exit 2
}

$snapshot = Get-Content -Raw -LiteralPath $LatestExport | ConvertFrom-Json
$exportedAt = $snapshot.ExportedAtUtc
$schema = $snapshot.SchemaVersion
$cityName = if ($snapshot.City.CityName) { $snapshot.City.CityName } else { '(unnamed / early city)' }

Write-Host 'CS2 Data Export OK' -ForegroundColor Green
Write-Host "  schema_version: $schema"
Write-Host "  exported_at_utc: $exportedAt"
Write-Host "  city: $cityName"
Write-Host "  path: $LatestExport"

$log = Join-Path $UserDataPath 'Logs\CS2DataExport.log'
if (Test-Path -LiteralPath $log) {
    Write-Host ''
    Write-Host 'Recent log lines:' -ForegroundColor Cyan
    Get-Content -LiteralPath $log -Tail 8
}
