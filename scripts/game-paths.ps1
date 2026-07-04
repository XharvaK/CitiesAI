# CitiesAI shared paths (override via environment or citiesai setup)

$script:UserDataPath = Join-Path $env:USERPROFILE 'AppData\LocalLow\Colossal Order\Cities Skylines II'
$script:ExportRoot = Join-Path $UserDataPath 'ModsData\CS2DataExport'
$script:LatestExport = Join-Path $ExportRoot 'latest.json'
$script:LocalModsPath = Join-Path $UserDataPath 'Mods'
$script:DataExportModPath = Join-Path $LocalModsPath 'CS2DataExport'
$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:DataExportSource = Join-Path $RepoRoot 'vendor\Cities2-DataExport'

# Optional overrides from citiesai config / env
if ($env:CITIES2_GAME_DIR) {
    $script:GameContentRoot = $env:CITIES2_GAME_DIR
} elseif (Test-Path 'C:\XboxGames') {
    $candidate = Get-ChildItem -Path 'C:\XboxGames\*\Content\Cities2_Data\Content\Game\Locale.cok' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($candidate) {
        $script:GameContentRoot = $candidate.Directory.Parent.Parent.Parent.Parent.FullName
    }
}

if ($script:GameContentRoot) {
    $script:GameManagedPath = Join-Path $GameContentRoot 'Cities2_Data\Managed'
    $script:GameToolchainRoot = Join-Path $GameContentRoot 'Cities2_Data\Content\Game\.ModdingToolchain'
    $script:ModPostProcessorPath = Join-Path $GameToolchainRoot 'ModPostProcessor\ModPostProcessor.exe'
    $script:ModPublisherPath = Join-Path $GameToolchainRoot 'ModPublisher\ModPublisher.exe'
}

if ($env:CITIESAI_EXPORT_PATH) {
    $script:LatestExport = $env:CITIESAI_EXPORT_PATH
}

$script:ToolPath = Join-Path $UserDataPath '.cache\Modding'
