#Requires -Version 5.1
<#
.SYNOPSIS
  Build and install CS2 Data Export for CitiesAI (Game Pass paths).

.DESCRIPTION
  Requires the in-game CS2 modding toolchain to be installed first.
  Run scripts/check-toolchain.ps1 to verify prerequisites.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\game-paths.ps1"

function Test-ToolchainReady {
    $checks = [ordered]@{
        ToolPathExists = Test-Path -LiteralPath $ToolPath
        ModPropsExists = Test-Path -LiteralPath (Join-Path $ToolPath 'Mod.props')
        CSII_TOOLPATH = [Environment]::GetEnvironmentVariable('CSII_TOOLPATH', 'User')
        CSII_MANAGEDPATH = [Environment]::GetEnvironmentVariable('CSII_MANAGEDPATH', 'User')
        CSII_UNITYMODPROJECTPATH = [Environment]::GetEnvironmentVariable('CSII_UNITYMODPROJECTPATH', 'User')
        CSII_MODPOSTPROCESSORPATH = [Environment]::GetEnvironmentVariable('CSII_MODPOSTPROCESSORPATH', 'User')
        UnityProjectExists = $false
    }

    if ($checks.CSII_UNITYMODPROJECTPATH) {
        $checks.UnityProjectExists = Test-Path -LiteralPath $checks.CSII_UNITYMODPROJECTPATH
    }

    return $checks
}

$toolchain = Test-ToolchainReady
$missing = @()
if (-not $toolchain.ToolPathExists) { $missing += '`.cache\Modding` folder missing' }
if (-not $toolchain.ModPropsExists) { $missing += 'Mod.props not deployed to user toolchain cache' }
if (-not $toolchain.CSII_TOOLPATH) { $missing += 'CSII_TOOLPATH user env var not set' }
if (-not $toolchain.CSII_MANAGEDPATH) { $missing += 'CSII_MANAGEDPATH user env var not set' }
if (-not $toolchain.CSII_UNITYMODPROJECTPATH) { $missing += 'CSII_UNITYMODPROJECTPATH user env var not set' }
if (-not $toolchain.UnityProjectExists) { $missing += 'Unity mod project not imported yet' }
if (-not $toolchain.CSII_MODPOSTPROCESSORPATH) { $missing += 'CSII_MODPOSTPROCESSORPATH user env var not set' }

if ($missing.Count -gt 0) {
    Write-Host 'CS2 modding toolchain is not ready yet.' -ForegroundColor Yellow
    foreach ($item in $missing) { Write-Host "  - $item" }
    Write-Host ''
    Write-Host 'In-game setup (one time):' -ForegroundColor Cyan
    Write-Host '  1. Launch Cities: Skylines II'
    Write-Host '  2. Options -> Modding'
    Write-Host '  3. Install/repair all toolchain dependencies until every row shows a green check'
    Write-Host '  4. Close the game, open a NEW terminal, then re-run:'
    Write-Host "     powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit 2
}

if (-not (Test-Path -LiteralPath (Join-Path $DataExportSource 'CS2DataExport.csproj'))) {
    throw "Source not found: $DataExportSource"
}

$env:DOTNET_ROLL_FORWARD = 'Major'
Push-Location -LiteralPath $DataExportSource
try {
    Remove-Item -LiteralPath .\obj -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath .\bin -Recurse -Force -ErrorAction SilentlyContinue
    dotnet build .\CS2DataExport.csproj -c Release -p:LangVersion=latest
    if ($LASTEXITCODE -ne 0) { throw "dotnet build failed with exit code $LASTEXITCODE" }

    $buildOut = Join-Path $PWD 'bin\Release\net48'
    if (-not (Test-Path -LiteralPath $buildOut)) {
        throw "Build output not found: $buildOut"
    }

    New-Item -ItemType Directory -Force -Path $DataExportModPath | Out-Null
    robocopy $buildOut $DataExportModPath /MIR | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }

    Write-Host "Installed mod to: $DataExportModPath" -ForegroundColor Green

    $localModsCache = Join-Path $UserDataPath '.cache\Mods\local'
    $localLink = Join-Path $localModsCache 'CS2DataExport'
    New-Item -ItemType Directory -Force -Path $localModsCache | Out-Null
    if (Test-Path -LiteralPath $localLink) {
        $item = Get-Item -LiteralPath $localLink -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            cmd /c "rmdir `"$localLink`"" | Out-Null
        } else {
            Remove-Item -LiteralPath $localLink -Recurse -Force
        }
    }
    cmd /c mklink /J "$localLink" "$DataExportModPath" | Out-Null
    Write-Host "Linked for Paradox Mods local scan: $localLink" -ForegroundColor Green
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host 'Next:' -ForegroundColor Cyan
Write-Host '  1. Launch CS2 and load a city'
Write-Host '  2. Enable CS2 Data Export in the mod list if needed'
Write-Host '  3. Wait up to 10 minutes (default export interval) or save/reload'
Write-Host "  4. Run: powershell -ExecutionPolicy Bypass -File `"$PSScriptRoot\verify-export.ps1`""
