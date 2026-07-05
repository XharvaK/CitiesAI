param(
    [Parameter(Mandatory = $true)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Set-FileLine {
    param([string]$Path, [string]$Pattern, [string]$Replacement)
    $text = Get-Content -LiteralPath $Path -Raw
    $updated = [regex]::Replace($text, $Pattern, $Replacement)
    if ($text -eq $updated) {
        throw "Pattern not found in $Path"
    }
    Set-Content -LiteralPath $Path -Value $updated -NoNewline
}

Set-FileLine (Join-Path $root "pyproject.toml") '(?m)^version = ".*"$' "version = `"$Version`""
Set-FileLine (Join-Path $root "citiesai\version.py") '(?m)^_FALLBACK_VERSION = ".*"$' "_FALLBACK_VERSION = `"$Version`""
Set-FileLine (Join-Path $root "packaging\CitiesAI.iss") '(?m)^#define MyAppVersion ".*"$' "#define MyAppVersion `"$Version`""
Set-FileLine (Join-Path $root "README.md") '(?m)CitiesAI-Setup-[\d.]+\.exe' "CitiesAI-Setup-$Version.exe"
Set-FileLine (Join-Path $root "README.md") '(?m)\*\*0\.[\d.]+\*\*' "**$Version**"

Write-Host "Bumped CitiesAI to $Version"
