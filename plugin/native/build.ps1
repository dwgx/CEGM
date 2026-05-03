# build.ps1 — compile cegm_plugin.c into CEGM-x64.dll for Cheat Engine.
#
# Auto-detects: a Visual Studio installation (via vswhere), the Cheat
# Engine install directory (via Start Menu shortcut). Override either
# with -CEDir / -OutDir.

[CmdletBinding()]
param(
    [string] $CEDir,
    [string] $OutDir = "$PSScriptRoot\dist",
    [ValidateSet("amd64", "x86")] [string] $Arch = "amd64",
    [switch] $InstallToCE
)

$ErrorActionPreference = "Stop"

# ── 1. Locate Visual Studio so we can run cl.exe ─────────────────────
$vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vsWhere)) {
    throw "vswhere.exe not found. Install Visual Studio 2022 with the C++ workload."
}
$vsRoot = & $vsWhere -latest -property installationPath
if (-not $vsRoot) { throw "No Visual Studio installation found." }

$devShell = "$vsRoot\Common7\Tools\Launch-VsDevShell.ps1"
if (-not (Test-Path $devShell)) { throw "Launch-VsDevShell.ps1 not found at $devShell." }

# ── 2. Locate Cheat Engine for the include path + optional install ──
if (-not $CEDir) {
    $shortcut = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Cheat Engine.lnk"
    if (Test-Path $shortcut) {
        $sh = New-Object -ComObject WScript.Shell
        $exePath = $sh.CreateShortcut($shortcut).TargetPath
        $CEDir = Split-Path -Parent $exePath
    }
}
if (-not $CEDir -or -not (Test-Path "$CEDir\plugins\cepluginsdk.h")) {
    throw "Cheat Engine plugins SDK not found. Pass -CEDir 'C:\Path\To\Cheat Engine'."
}

Write-Host "VS    : $vsRoot"
Write-Host "CE    : $CEDir"
Write-Host "Arch  : $Arch"

# ── 3. Compile inside a Dev Shell so cl.exe is on PATH ───────────────
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$dllName = if ($Arch -eq "amd64") { "CEGM-x64.dll" } else { "CEGM-x86.dll" }
$out = Join-Path $OutDir $dllName

# Use a one-shot script-block so the dev-shell environment dies cleanly.
$src    = Join-Path $PSScriptRoot "cegm_plugin.c"
$def    = Join-Path $PSScriptRoot "cegm_plugin.def"
$incCE  = Join-Path $CEDir "plugins"

& powershell -NoProfile -ExecutionPolicy Bypass -Command @"
    & '$devShell' -Arch $Arch -SkipAutomaticLocation
    Set-Location '$PSScriptRoot'
    `$ErrorActionPreference = 'Stop'
    cl.exe /nologo /LD /MD /O2 /W3 /utf-8 /I '$incCE' '$src' /link /DEF:'$def' /OUT:'$out'
    if (`$LASTEXITCODE -ne 0) { throw 'cl.exe failed' }
"@
if ($LASTEXITCODE -ne 0) { throw "Build failed." }

Write-Host "`nBuilt: $out"

if ($InstallToCE) {
    $dest = Join-Path $CEDir "plugins"
    Copy-Item $out $dest -Force
    Write-Host "Installed to $dest\$dllName"
    Write-Host "Open CE → Settings → Plugins → tick the box next to '$([System.IO.Path]::GetFileNameWithoutExtension($dllName))' and click OK."
}
