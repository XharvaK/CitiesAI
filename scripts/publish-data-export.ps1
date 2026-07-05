#Requires -Version 5.1
<#
.SYNOPSIS
  Publish CS2 Data Export to Paradox Mods (Path A — ModPublisher).

.DESCRIPTION
  Requires:
  - CS2 modding toolchain (Options -> Modding, all green)
  - Paradox account logged in-game at least once, OR pdx_account.txt on Desktop
  - Properties/PublishConfiguration.xml filled in (thumbnail, screenshots, version)

  First publish: leaves ModId empty in PublishConfiguration.xml; copy Mod ID from output.
  Updates: set ModId, bump ModVersion and ChangeLog, use PublishNewVersion profile.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $RepoRoot 'vendor\Cities2-DataExport'
$Profile = 'PublishNewMod'
if ($args -contains '--update') { $Profile = 'PublishNewVersion' }

if (-not (Test-Path -LiteralPath (Join-Path $Source 'Properties\Thumbnail.png'))) {
    throw 'Missing Properties\Thumbnail.png — add publish assets before publishing.'
}

$env:DOTNET_ROLL_FORWARD = 'Major'
Push-Location -LiteralPath $Source
try {
    Write-Host "Publishing with profile: $Profile" -ForegroundColor Cyan
    dotnet publish .\CS2DataExport.csproj -p:PublishProfile=$Profile -p:LangVersion=latest
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'dotnet publish failed (CS2 may be locking Mods\CS2DataExport). Trying ModPublisher with build output...' -ForegroundColor Yellow
        $build = Join-Path $Source 'bin\Release\net48'
        $cfg = Join-Path $Source 'Properties\PublishConfiguration.xml'
        if (-not (Test-Path -LiteralPath $build)) { throw 'Build output not found.' }
        & $env:CSII_MODPUBLISHERPATH $(if ($Profile -eq 'PublishNewVersion') { 'NewVersion' } else { 'Publish' }) $cfg -c $build -v
        if ($LASTEXITCODE -ne 0) { throw "ModPublisher failed with exit code $LASTEXITCODE" }
    }
    Write-Host ''
    Write-Host 'If this was the first publish, copy the Mod ID from the log above into Properties\PublishConfiguration.xml <ModId Value="..." />' -ForegroundColor Green
}
finally {
    Pop-Location
}
