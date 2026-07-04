#Requires -Version 5.1
<#
.SYNOPSIS
  Build CitiesAI release: mod staging, PyInstaller exe, optional Inno Setup installer.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

Write-Host '== Stage mod (if toolchain available) ==' -ForegroundColor Cyan
$Stage = Join-Path $RepoRoot 'packaging\bundled\CS2DataExport'
if (-not (Test-Path -LiteralPath (Join-Path $Stage 'CS2DataExport.dll'))) {
    try {
        & (Join-Path $RepoRoot 'scripts\build-mod-release.ps1')
    } catch {
        Write-Host "Mod staging skipped or failed: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "Using existing staged mod: $Stage" -ForegroundColor Green
}

Write-Host '== Brand assets ==' -ForegroundColor Cyan
uv sync --group dev
uv run python scripts\generate-brand-assets.py

Write-Host '== PyInstaller ==' -ForegroundColor Cyan
uv pip install pyinstaller
uv run pyinstaller packaging\citiesai.spec --noconfirm --distpath dist --workpath build\pyinstaller

$Exe = Join-Path $RepoRoot 'dist\CitiesAI.exe'
if (-not (Test-Path -LiteralPath $Exe)) {
    throw "PyInstaller output not found: $Exe"
}
Write-Host "Built: $Exe" -ForegroundColor Green

$Iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if ($Iscc) {
    Write-Host '== Inno Setup ==' -ForegroundColor Cyan
    & $Iscc (Join-Path $RepoRoot 'packaging\CitiesAI.iss')
    Write-Host 'Installer built under dist\' -ForegroundColor Green
} else {
    Write-Host 'Inno Setup not found. Ship dist\CitiesAI.exe or install Inno Setup 6.' -ForegroundColor Yellow
}
