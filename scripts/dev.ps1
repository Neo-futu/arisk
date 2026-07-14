Param(
    [ValidateSet("web", "agent", "full")]
    [string]$Profile = "web",

    [switch]$NoFrontend,
    [switch]$NoBackend,
    [switch]$NoEntry,
    [switch]$NoProcessing,
    [switch]$WithMcp,
    [switch]$WithMcpGateway,
    [switch]$WithInternalMcp,
    [switch]$WithWindMcp,

    [ValidateSet("processing", "entry", "backend", "frontend", "mcp-gateway", "internal-mcp", "wind-mcp")]
    [string]$Only,

    [ValidateSet("processing", "entry", "backend", "frontend", "mcp-gateway", "internal-mcp", "wind-mcp")]
    [string[]]$Parts,

    [switch]$ListParts,
    [switch]$DryRun,

    [Alias("?")]
    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Add-Flag {
    param(
        [System.Collections.Generic.List[string]]$ArgsList,
        [bool]$Condition,
        [string]$Flag
    )
    if ($Condition) {
        $ArgsList.Add($Flag) | Out-Null
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if ($Help.IsPresent) {
    python scripts/dev.py --help
    exit $LASTEXITCODE
}

if ($ListParts.IsPresent) {
    python scripts/dev.py --list-parts
    exit $LASTEXITCODE
}

$argsList = [System.Collections.Generic.List[string]]::new()
$argsList.Add("scripts/dev.py") | Out-Null
$argsList.Add("--profile") | Out-Null
$argsList.Add($Profile) | Out-Null

Add-Flag -ArgsList $argsList -Condition $NoFrontend.IsPresent -Flag "--no-frontend"
Add-Flag -ArgsList $argsList -Condition $NoBackend.IsPresent -Flag "--no-backend"
Add-Flag -ArgsList $argsList -Condition $NoEntry.IsPresent -Flag "--no-entry"
Add-Flag -ArgsList $argsList -Condition $NoProcessing.IsPresent -Flag "--no-processing"
Add-Flag -ArgsList $argsList -Condition $WithMcp.IsPresent -Flag "--with-mcp"
Add-Flag -ArgsList $argsList -Condition $WithMcpGateway.IsPresent -Flag "--with-mcp-gateway"
Add-Flag -ArgsList $argsList -Condition $WithInternalMcp.IsPresent -Flag "--with-internal-mcp"
Add-Flag -ArgsList $argsList -Condition $WithWindMcp.IsPresent -Flag "--with-wind-mcp"

if ($Only) {
    $argsList.Add("--only") | Out-Null
    $argsList.Add($Only) | Out-Null
}

if ($Parts -and $Parts.Count -gt 0) {
    $argsList.Add("--parts") | Out-Null
    foreach ($part in $Parts) {
        $argsList.Add($part) | Out-Null
    }
}

if ($DryRun.IsPresent) {
    $argsList.Add("--dry-run") | Out-Null
}

Write-Host "FSI dev launcher: python $($argsList -join ' ')" -ForegroundColor Cyan
python @argsList
