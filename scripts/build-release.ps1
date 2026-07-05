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

Write-Host '== Feedback webhook (optional) ==' -ForegroundColor Cyan
$BundledDir = Join-Path $RepoRoot 'packaging\bundled'
$WebhookBundle = Join-Path $BundledDir 'feedback_webhook.url'
$SecretsFile = Join-Path $RepoRoot 'packaging\secrets.local.env'
New-Item -ItemType Directory -Force -Path $BundledDir | Out-Null

if (Test-Path -LiteralPath $SecretsFile) {
    Get-Content -LiteralPath $SecretsFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $eq = $line.IndexOf('=')
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
        if ($name) { Set-Item -Path "env:$name" -Value $value }
    }
}

$WebhookUrl = $env:CITIESAI_DISCORD_WEBHOOK
if ($WebhookUrl) {
    if ($WebhookUrl -notmatch '^https://discord\.com/api/webhooks/') {
        throw 'CITIESAI_DISCORD_WEBHOOK must start with https://discord.com/api/webhooks/'
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($WebhookBundle, $WebhookUrl, $utf8NoBom)
    Write-Host "Bundled Discord webhook for release: $WebhookBundle" -ForegroundColor Green
} elseif (Test-Path -LiteralPath $WebhookBundle) {
    Write-Host "Keeping existing bundled webhook: $WebhookBundle" -ForegroundColor Green
} else {
    Write-Host 'No Discord webhook configured. Feedback will save locally only in shipped builds.' -ForegroundColor Yellow
    Write-Host 'Copy packaging/secrets.local.env.example to packaging/secrets.local.env and set CITIESAI_DISCORD_WEBHOOK.' -ForegroundColor Yellow
}

Write-Host '== PyInstaller ==' -ForegroundColor Cyan
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
    $Version = (uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
    & $Iscc "/DMyAppVersion=$Version" (Join-Path $RepoRoot 'packaging\CitiesAI.iss')
    Write-Host 'Installer built under dist\' -ForegroundColor Green
} else {
    Write-Host 'Inno Setup not found. Ship dist\CitiesAI.exe or install Inno Setup 6.' -ForegroundColor Yellow
}
