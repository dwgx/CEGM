<#
.SYNOPSIS
    Build the CEGM release ZIP from current source.

.DESCRIPTION
    Collects all plugin files (Lua autorun + C DLL), copies them into
    release/staging/ with the correct directory layout, then creates
    CEGM-plugin-v<version>.zip in release/dist/.

    Also rebuilds the C DLL if VS 2022 is available.

.EXAMPLE
    .\scripts\release.ps1

.EXAMPLE
    .\scripts\release.ps1 -SkipDllBuild
#>

[CmdletBinding()]
param(
    [switch]$SkipDllBuild,
    [string]$Version = "0.1.0a1"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$StagingDir = Join-Path $RepoRoot "release\staging"
$DistDir = Join-Path $RepoRoot "release\dist"
$PluginDir = Join-Path $RepoRoot "plugin"
$VendorDir = Join-Path $RepoRoot "vendor\cheatengine-mcp-bridge"

function Write-Step { param([string]$M) Write-Host "  [$((Get-Date -Format 'HH:mm:ss'))] $M" -ForegroundColor Cyan }
function Write-OK   { param([string]$M) Write-Host "    OK  $M" -ForegroundColor Green }
function Write-Warn { param([string]$M) Write-Host "    WARN $M" -ForegroundColor Yellow }

# ── clean staging ──────────────────────────────────────────────────────

Write-Step "Cleaning staging directory..."
if (Test-Path $StagingDir) {
    Get-ChildItem -Path $StagingDir -Exclude "INSTALL.txt","LICENSE*" -Recurse |
        Where-Object { -not $_.PSIsContainer } | Remove-Item -Force
    Get-ChildItem -Path $StagingDir -Exclude "INSTALL.txt","LICENSE*" -Directory |
        Sort-Object FullName -Descending | Remove-Item -Recurse -Force
}
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

# ── autorun/cegm_loader.lua ────────────────────────────────────────────

Write-Step "Copying cegm_loader.lua..."
New-Item -ItemType Directory -Path "$StagingDir\autorun" -Force | Out-Null
Copy-Item -Path "$PluginDir\cegm_loader.lua" -Destination "$StagingDir\autorun\" -Force
Write-OK "autorun\cegm_loader.lua"

# ── autorun/CEGM/ ──────────────────────────────────────────────────────

Write-Step "Copying autorun/CEGM/..."
$cegmDest = "$StagingDir\autorun\CEGM"
New-Item -ItemType Directory -Path $cegmDest -Force | Out-Null

# cegm.lua
Copy-Item -Path "$PluginDir\cegm.lua" -Destination $cegmDest -Force
Write-OK "  cegm.lua"

# ce_mcp_bridge.lua (vendored)
# Try multiple locations (upstream may change directory structure)
$bridgeCandidates = @(
    "$VendorDir\MCP_Server\ce_mcp_bridge.lua",
    "$VendorDir\plugin\ce_mcp_bridge.lua"
)
$bridge = $null
foreach ($c in $bridgeCandidates) { if (Test-Path $c) { $bridge = $c; break } }
if ($bridge) {
    Copy-Item -Path $bridge -Destination $cegmDest -Force
    Write-OK "  ce_mcp_bridge.lua"
} else { Write-Warn "  ce_mcp_bridge.lua NOT FOUND" }

# lib/
$libSrc = "$PluginDir\lib"
if (Test-Path $libSrc) {
    $libDest = "$cegmDest\lib"
    New-Item -ItemType Directory -Path $libDest -Force | Out-Null
    Copy-Item -Path "$libSrc\*" -Destination $libDest -Force -Recurse
    Write-OK "  lib/ ($((Get-ChildItem $libSrc -File | Measure-Object).Count) files)"
} else { Write-Warn "  lib/ not found" }

# ── plugins/CEGM-x64.dll ───────────────────────────────────────────────

Write-Step "Preparing CEGM-x64.dll..."
$dllDest = "$StagingDir\plugins"
New-Item -ItemType Directory -Path $dllDest -Force | Out-Null

if (-not $SkipDllBuild -and (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    Write-Step "  Building DLL with MSVC..."
    Push-Location "$PluginDir\native"
    try {
        & .\build.ps1 2>&1 | ForEach-Object { Write-Host "    $_" }
        if (Test-Path "dist\CEGM-x64.dll") {
            Copy-Item -Path "dist\CEGM-x64.dll" -Destination $dllDest -Force
            Write-OK "  CEGM-x64.dll (freshly built)"
        }
    } finally { Pop-Location }
} else {
    $prebuilt = "$PluginDir\native\dist\CEGM-x64.dll"
    if (Test-Path $prebuilt) {
        Copy-Item -Path $prebuilt -Destination $dllDest -Force
        Write-OK "  CEGM-x64.dll (prebuilt)"
    } else { Write-Warn "  CEGM-x64.dll not found" }
}

# ── build ZIP ──────────────────────────────────────────────────────────

$zipName = "CEGM-plugin-v$Version.zip"
$zipPath = Join-Path $DistDir $zipName

Write-Step "Creating $zipName..."
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$StagingDir\*" -DestinationPath $zipPath -Force
$zipSize = [math]::Round((Get-Item $zipPath).Length / 1KB, 0)
Write-OK "$zipName ($zipSize KB)"

# ── broker wheel backup ────────────────────────────────────────────────

$wheel = Get-ChildItem "$RepoRoot\broker\dist\*.whl" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($wheel) {
    Copy-Item -Path $wheel.FullName -Destination $DistDir -Force
    Write-OK "broker wheel: $($wheel.Name)"
}

# ── summary ────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Release v$Version built" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Files in release/staging/"
Get-ChildItem -Path $StagingDir -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($StagingDir.Length + 1)
    Write-Host "    $rel"
}
Write-Host ""
Write-Host "  Output: $zipPath"
Write-Host ""
Write-Host "  To publish on GitHub:"
Write-Host "    gh release create v$Version $zipPath --title 'CEGM v$Version' --notes 'See README for install instructions.'"
Write-Host ""
