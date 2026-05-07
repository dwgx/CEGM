<#
.SYNOPSIS
    One-click installer for CEGM (CheatEngineGM).

.DESCRIPTION
    Detects Cheat Engine 7.5+ installation, copies the Lua autorun bundle
    and C plugin DLL into <CE>, installs cegm-broker via uv, creates a
    desktop shortcut.

    Can be run from the CEGM repo root (dev install) or standalone from
    the release ZIP.

.PARAMETER CePath
    Explicit path to Cheat Engine install directory. Auto-detected if omitted.

.PARAMETER NoShortcut
    Skip creating the desktop shortcut.

.PARAMETER BrokerOnly
    Only install the broker; skip plugin copy.

.PARAMETER FromZip
    Path to an extracted CEGM-plugin ZIP. Copies files from there instead
    of the repo source tree.

.EXAMPLE
    .\install.ps1

.EXAMPLE
    .\install.ps1 -CePath "D:\Games\Cheat Engine 7.5"

.EXAMPLE
    .\install.ps1 -FromZip ".\CEGM-plugin-v0.1.0a1"
#>

[CmdletBinding()]
param(
    [string]$CePath,
    [switch]$NoShortcut,
    [switch]$BrokerOnly,
    [string]$FromZip
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$Port = 27077
$DashboardUrl = "http://127.0.0.1:$Port/"

# ── helpers ────────────────────────────────────────────────────────────

function Write-Step { param([string]$M) Write-Host "  [$((Get-Date -Format 'HH:mm:ss'))] $M" -ForegroundColor Cyan }
function Write-OK   { param([string]$M) Write-Host "    OK  $M" -ForegroundColor Green }
function Write-Warn { param([string]$M) Write-Host "    WARN $M" -ForegroundColor Yellow }
function Write-Fail { param([string]$M) Write-Host "    FAIL $M" -ForegroundColor Red }

# ── resolve source directory ───────────────────────────────────────────

function Get-SourceDir {
    if ($FromZip) {
        if (Test-Path $FromZip) { return (Resolve-Path $FromZip).Path }
        Write-Fail "FromZip path not found: $FromZip"
        return $null
    }
    # Running from repo root: scripts/install.ps1 → parent is repo root
    $myDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $repo = Split-Path -Parent $myDir
    if (Test-Path "$repo\web\index.html") { return $repo }
    # Running from release staging dir
    if (Test-Path "$PSScriptRoot\autorun\CEGM\cegm.lua") { return $PSScriptRoot }
    return $null
}

# ── locate Cheat Engine ────────────────────────────────────────────────

function Find-CheatEngine {
    if ($CePath) {
        # Check for cheatengine-x86_64.exe OR cheatengine-i386.exe
        if ((Test-Path "$CePath\cheatengine-x86_64.exe") -or (Test-Path "$CePath\cheatengine-i386.exe")) {
            return (Resolve-Path $CePath).Path
        }
        Write-Fail "$CePath does not contain cheatengine-*.exe"
        return $null
    }

    # Common install paths, newest versions first
    $versions = @("7.8", "7.7", "7.6", "7.5")
    $bases = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "C:\", "D:\")
    $candidates = @()
    foreach ($b in $bases) {
        foreach ($v in $versions) {
            $candidates += "$b\Cheat Engine $v"
        }
    }
    # Also scan for any "Cheat Engine*" folder in common locations
    foreach ($b in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, "C:\", "D:\")) {
        try {
            $found = Get-ChildItem -Path $b -Directory -Filter "Cheat Engine*" -ErrorAction SilentlyContinue |
                     Where-Object { (Test-Path "$_\cheatengine-x86_64.exe") -or (Test-Path "$_\cheatengine-i386.exe") } |
                     Sort-Object Name -Descending
            foreach ($d in $found) { $candidates += $d.FullName }
        } catch {}
    }

    $seen = @{}
    foreach ($c in $candidates) {
        $c = if (Test-Path $c) { (Resolve-Path $c).Path } else { continue }
        if ($seen[$c]) { continue }; $seen[$c] = $true
        if ((Test-Path "$c\cheatengine-x86_64.exe") -or (Test-Path "$c\cheatengine-i386.exe")) {
            return $c
        }
    }
    return $null
}

# ── install uv ─────────────────────────────────────────────────────────

function Install-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-OK "uv found: $(uv --version)"
        return $true
    }
    Write-Step "Installing uv (Python package manager)..."
    try {
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        if (Get-Command uv -ErrorAction SilentlyContinue) { Write-OK "uv installed"; return $true }
        $env:Path = "$env:APPDATA\uv;$env:Path"
        if (Get-Command uv -ErrorAction SilentlyContinue) { Write-OK "uv installed"; return $true }
    } catch { Write-Warn "uv install failed: $_" }
    return $false
}

# ── install broker ─────────────────────────────────────────────────────

function Install-Broker {
    Write-Step "Installing cegm-broker..."
    $existing = uv tool list 2>$null | Select-String "cegm-broker"
    if ($existing) {
        Write-Step "Upgrading existing cegm-broker..."
        uv tool upgrade cegm-broker 2>&1
        if ($LASTEXITCODE -eq 0) { Write-OK "cegm-broker upgraded"; return $true }
    }
    uv tool install cegm-broker 2>&1
    if ($LASTEXITCODE -eq 0) { Write-OK "cegm-broker installed"; return $true }
    Write-Fail "cegm-broker install failed"
    return $false
}

# ── copy plugin files ──────────────────────────────────────────────────

function Copy-PluginFiles {
    param([string]$CeDir, [string]$SourceDir)

    # ── cegm_loader.lua → <CE>/autorun/cegm_loader.lua ──
    $loader = Join-Path $SourceDir "autorun\cegm_loader.lua"
    if (-not (Test-Path $loader)) {
        # dev mode: from repo plugin/ dir
        $loader = Join-Path $SourceDir "plugin\cegm_loader.lua"
    }
    if (Test-Path $loader) {
        $destDir = Join-Path $CeDir "autorun"
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        Copy-Item -Path $loader -Destination $destDir -Force
        Write-OK "cegm_loader.lua → autorun\"
    } else { Write-Warn "cegm_loader.lua not found" }

    # ── CEGM/ folder → <CE>/autorun/CEGM/ ──
    $cegmDir = Join-Path $SourceDir "autorun\CEGM"
    if (-not (Test-Path $cegmDir)) { $cegmDir = Join-Path $SourceDir "plugin" }
    if (Test-Path $cegmDir) {
        $destDir = Join-Path $CeDir "autorun\CEGM"
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        Get-ChildItem -Path $cegmDir -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($cegmDir.Length + 1)
            $d = Join-Path $destDir $rel
            $dp = Split-Path -Parent $d
            if (-not (Test-Path $dp)) { New-Item -ItemType Directory -Path $dp -Force | Out-Null }
            Copy-Item -Path $_.FullName -Destination $d -Force
            Write-OK "autorun\CEGM\$rel"
        }
    } else { Write-Warn "CEGM autorun directory not found at $cegmDir" }

    # ── vendored ce_mcp_bridge.lua → <CE>/autorun/CEGM/ ──
    $bridgeCandidates = @(
        Join-Path $SourceDir "autorun\CEGM\ce_mcp_bridge.lua"
        Join-Path $SourceDir "vendor\cheatengine-mcp-bridge\MCP_Server\ce_mcp_bridge.lua"
        Join-Path $SourceDir "vendor\cheatengine-mcp-bridge\plugin\ce_mcp_bridge.lua"
    )
    $bridge = $null
    foreach ($c in $bridgeCandidates) { if (Test-Path $c) { $bridge = $c; break } }
    if ($bridge) {
        $destDir = Join-Path $CeDir "autorun\CEGM"
        Copy-Item -Path $bridge -Destination $destDir -Force
        Write-OK "ce_mcp_bridge.lua → autorun\CEGM\"
    } else { Write-Warn "ce_mcp_bridge.lua not found" }

    # ── CEGM-x64.dll → <CE>/plugins/ ──
    $dll = Join-Path $SourceDir "plugins\CEGM-x64.dll"
    if (-not (Test-Path $dll)) { $dll = Join-Path $SourceDir "plugin\native\dist\CEGM-x64.dll" }
    if (Test-Path $dll) {
        $destDir = Join-Path $CeDir "plugins"
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        Copy-Item -Path $dll -Destination $destDir -Force
        Write-OK "CEGM-x64.dll → plugins\"
    } else { Write-Warn "CEGM-x64.dll not found — C plugin won't be available" }

    Write-Host ""
    Write-Host "  IMPORTANT: In Cheat Engine, go to Edit → Settings → Plugins" -ForegroundColor Yellow
    Write-Host "  and tick the box next to CEGM-x64, then click OK." -ForegroundColor Yellow
}

# ── desktop shortcut ───────────────────────────────────────────────────

function New-DesktopShortcut {
    if ($NoShortcut) { return }
    Write-Step "Creating desktop shortcut..."
    try {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $sc = Join-Path $desktop "CEGM Dashboard.url"
        @"
[InternetShortcut]
URL=$DashboardUrl
IconFile=%SystemRoot%\System32\SHELL32.dll
IconIndex=13
"@ | Set-Content -Path $sc -Encoding ASCII
        Write-OK "Shortcut: $sc"
    } catch { Write-Warn "Shortcut failed: $_" }
}

# ── main ────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  CEGM (CheatEngineGM) Installer" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

$srcDir = Get-SourceDir
if (-not $srcDir) {
    Write-Fail "Could not determine source directory."
    Write-Fail "Run from CEGM repo root, or use -FromZip to specify extracted ZIP path."
    exit 1
}
Write-OK "Source: $srcDir"

# 1. uv
if (-not (Install-Uv)) {
    Write-Host "Cannot proceed without uv." -ForegroundColor Red
    Write-Host "Install: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

# 2. broker
if (-not (Install-Broker)) { exit 1 }

# 3. CE + plugin
if (-not $BrokerOnly) {
    $ceDir = Find-CheatEngine
    if (-not $ceDir) {
        Write-Warn "Could not auto-detect Cheat Engine installation."
        Write-Host ""
        Write-Host "  Please specify manually:" -ForegroundColor Yellow
        Write-Host "    .\install.ps1 -CePath 'C:\Path\To\Cheat Engine 7.5'" -ForegroundColor Yellow
        Write-Host "  Or use -BrokerOnly to skip plugin installation." -ForegroundColor Yellow
    } else {
        Write-OK "Cheat Engine: $ceDir"
        Write-Step "Copying plugin files..."
        Copy-PluginFiles -CeDir $ceDir -SourceDir $srcDir
    }
}

# 4. shortcut
New-DesktopShortcut

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Dashboard:  $DashboardUrl"
Write-Host "  MCP URL:    $DashboardUrl`mcp"
Write-Host ""
Write-Host "  Start:      cegm-broker --dev"
Write-Host "  Then open:  $DashboardUrl"
Write-Host ""
