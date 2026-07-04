#Requires -Version 5.1
<#
.SYNOPSIS
  Build CS2 Data Export mod and stage DLLs for CitiesAI installer bundling.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $RepoRoot 'vendor\Cities2-DataExport'
$BuildOut = Join-Path $Source 'bin\Release\net48'
$Stage = Join-Path $RepoRoot 'packaging\bundled\CS2DataExport'

& (Join-Path $RepoRoot 'scripts\install-data-export.ps1')
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path -LiteralPath $BuildOut)) {
    throw "Build output not found: $BuildOut"
}

New-Item -ItemType Directory -Force -Path $Stage | Out-Null
robocopy $BuildOut $Stage /MIR | Out-Null
if ($LASTEXITCODE -gt 7) {
    throw "robocopy staging failed with exit code $LASTEXITCODE"
}

Write-Host "Staged mod for bundling: $Stage" -ForegroundColor Green
