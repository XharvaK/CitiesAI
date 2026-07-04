#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\game-paths.ps1"

Write-Host 'CitiesAI Phase 2 — toolchain check' -ForegroundColor Cyan
Write-Host "Game content: $GameContentRoot"
Write-Host "User data:    $UserDataPath"
Write-Host "Toolchain:    $ToolPath"
Write-Host ''

$rows = [ordered]@{
    'Game.dll (Managed)' = Test-Path -LiteralPath (Join-Path $GameManagedPath 'Game.dll')
    'Bundled ModPostProcessor' = Test-Path -LiteralPath $ModPostProcessorPath
    'User .cache\Modding' = Test-Path -LiteralPath $ToolPath
    'User Mod.props' = Test-Path -LiteralPath (Join-Path $ToolPath 'Mod.props')
    'CSII_TOOLPATH env' = [bool][Environment]::GetEnvironmentVariable('CSII_TOOLPATH', 'User')
    'CSII_MANAGEDPATH env' = [bool][Environment]::GetEnvironmentVariable('CSII_MANAGEDPATH', 'User')
    'CSII_UNITYMODPROJECTPATH env' = [bool][Environment]::GetEnvironmentVariable('CSII_UNITYMODPROJECTPATH', 'User')
    'UnityModsProject folder' = $false
    'CS2DataExport mod installed' = Test-Path -LiteralPath $DataExportModPath
    'latest.json export' = Test-Path -LiteralPath $LatestExport
}

$unityPath = [Environment]::GetEnvironmentVariable('CSII_UNITYMODPROJECTPATH', 'User')
if ($unityPath) {
    $rows['UnityModsProject folder'] = Test-Path -LiteralPath $unityPath
}

$readyToBuild = $rows['User .cache\Modding'] -and $rows['User Mod.props'] -and $rows['CSII_TOOLPATH env'] -and $rows['CSII_MANAGEDPATH env'] -and $rows['CSII_UNITYMODPROJECTPATH env'] -and $rows['UnityModsProject folder']

foreach ($entry in $rows.GetEnumerator()) {
    $mark = if ($entry.Value) { '[ok]' } else { '[--]' }
    Write-Host "$mark $($entry.Key)"
}

Write-Host ''
if ($readyToBuild) {
    Write-Host 'Toolchain looks ready. Run scripts/install-data-export.ps1' -ForegroundColor Green
    exit 0
}

Write-Host 'Toolchain not ready. Install it in-game: Options -> Modding -> install all dependencies.' -ForegroundColor Yellow
exit 2
