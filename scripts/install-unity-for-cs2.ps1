#Requires -Version 5.1
<#
.SYNOPSIS
  Install Unity 2022.3.62f2 for CS2 modding toolchain (bypasses in-game hung installer).

.DESCRIPTION
  CS2's in-game Unity installer often hangs with an empty target folder.
  This script installs via Unity Hub CLI, then links the path CS2 expects.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$HubExe = 'C:\Program Files\Unity Hub\Unity Hub.exe'
$Version = '2022.3.62f2'
$Changeset = '7670c08855a9'
$HubEditorRoot = 'C:\Users\Xharv\Unity\Hub\Editor'
$HubEditorPath = Join-Path $HubEditorRoot $Version
$HubUnityExe = Join-Path $HubEditorPath 'Editor\Unity.exe'

# CS2 appends "\Unity {version}" to the installation directory you set in Options.
# Set Options -> Modding -> Unity installation directory to: C:\Users\Xharv\Unity\2022.3.62f2
$Cs2UnityRoot = 'C:\Users\Xharv\Unity\2022.3.62f2'
$Cs2ExpectedPath = Join-Path $Cs2UnityRoot "Unity $Version"
$Cs2UnityExe = Join-Path $Cs2ExpectedPath 'Editor\Unity.exe'

if (-not (Test-Path -LiteralPath $HubExe)) {
    throw "Unity Hub not found at $HubExe"
}

Write-Host "Setting Hub install path: $HubEditorRoot" -ForegroundColor Cyan
& $HubExe -- --headless install-path -s $HubEditorRoot | Out-Null

if (-not (Test-Path -LiteralPath $HubUnityExe)) {
    Write-Host "Installing Unity $Version via Hub CLI (large download, 10-30 min)..." -ForegroundColor Cyan
    & $HubExe -- --headless install --version $Version --changeset $Changeset --module windows-il2cpp
    if ($LASTEXITCODE -ne 0) {
        throw "Hub install failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $HubUnityExe)) {
    throw "Unity.exe not found after install: $HubUnityExe"
}

Write-Host "Unity installed at: $HubUnityExe" -ForegroundColor Green

# Bridge CS2 expected folder layout
New-Item -ItemType Directory -Force -Path $Cs2UnityRoot | Out-Null
if (Test-Path -LiteralPath $Cs2ExpectedPath) {
    $item = Get-Item -LiteralPath $Cs2ExpectedPath -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        Write-Host "CS2 bridge link already exists: $Cs2ExpectedPath"
    } elseif (-not (Test-Path -LiteralPath $Cs2UnityExe)) {
        Remove-Item -LiteralPath $Cs2ExpectedPath -Recurse -Force
        cmd /c mklink /J "$Cs2ExpectedPath" "$HubEditorPath"
    }
} else {
    cmd /c mklink /J "$Cs2ExpectedPath" "$HubEditorPath"
}

if (-not (Test-Path -LiteralPath $Cs2UnityExe)) {
    throw "CS2 bridge failed; expected $Cs2UnityExe"
}

Write-Host "CS2 bridge ready: $Cs2UnityExe" -ForegroundColor Green
Write-Host ''
Write-Host 'Next in CS2:' -ForegroundColor Cyan
Write-Host "  1. Quit and reopen the game"
Write-Host "  2. Options -> Modding -> Unity installation directory: $Cs2UnityRoot"
Write-Host '  3. Use Repair (not a fresh Install to Program Files)'
Write-Host '  4. Let Unity mod project + C# template finish'
