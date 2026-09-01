# Pack PhotosXAgent into a one-click deploy zip (no venv / node_modules / secrets).
# Usage:  .\scripts\pack_release.ps1
#         .\scripts\pack_release.ps1 -OutDir D:\releases

[CmdletBinding()]
param(
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) {
    throw "Cannot locate project root from scripts/pack_release.ps1"
}

Set-Location $Root

$versionFile = Join-Path $Root "VERSION"
$version = if (Test-Path $versionFile) {
    (Get-Content $versionFile -Raw).Trim()
} else {
    "0.0.0"
}

if (-not $OutDir) {
    $OutDir = Split-Path -Parent $Root
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$stamp = Get-Date -Format "yyyyMMdd"
$zipName = "PhotosXAgent-v$version-deploy-$stamp.zip"
$zipPath = Join-Path $OutDir $zipName
$stageRoot = Join-Path $env:TEMP ("photosx-pack-" + [guid]::NewGuid().ToString("N"))
$stage = Join-Path $stageRoot "PhotosXAgent"

Write-Host "Project : $Root" -ForegroundColor Cyan
Write-Host "Staging : $stage" -ForegroundColor Cyan
Write-Host "Output  : $zipPath" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $stage | Out-Null

$excludeDirNames = @(
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".idea", ".vscode",
    "dist", "build", "logs", ".cursor", "photosxagent.egg-info", "_vendor"
)
$excludeFileNames = @(".env", ".DS_Store")
$excludeGlob = @("*.pyc", "*.pyo", "*.log", "*.local")

function Test-ExcludedPath([string]$FullPath, [string]$RelativePath) {
    $parts = $RelativePath -split '[\\/]'
    foreach ($p in $parts) {
        if ($excludeDirNames -contains $p) { return $true }
    }
    $name = Split-Path -Leaf $FullPath
    if ($excludeFileNames -contains $name) { return $true }
    foreach ($g in $excludeGlob) {
        if ($name -like $g) { return $true }
    }
    # skip large upload/topic runtime data; keep empty placeholders via later mkdir
    if ($RelativePath -match '^(data[\\/]uploads|data[\\/]topics)([\\/]|$)') {
        if ($name -ne ".gitkeep") { return $true }
    }
    return $false
}

Get-ChildItem -Path $Root -Recurse -Force | ForEach-Object {
    $rel = $_.FullName.Substring($Root.Length).TrimStart('\', '/')
    if (-not $rel) { return }
    if (Test-ExcludedPath $_.FullName $rel) { return }

    $dest = Join-Path $stage $rel
    if ($_.PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
    } else {
        $parent = Split-Path -Parent $dest
        if (-not (Test-Path $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
    }
}

# Ensure empty data dirs exist in package
@(
    "data\uploads",
    "data\topics"
) | ForEach-Object {
    $d = Join-Path $stage $_
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    Set-Content -Path (Join-Path $d ".gitkeep") -Value "" -Encoding utf8
}

# Ensure .env is not present; keep example
$envInStage = Join-Path $stage ".env"
if (Test-Path $envInStage) { Remove-Item $envInStage -Force }

# Ensure launcher exists
if (-not (Test-Path (Join-Path $stage "start_dev.ps1"))) {
    throw "start_dev.ps1 missing in staging — abort"
}
if (-not (Test-Path (Join-Path $stage "start.bat"))) {
    throw "start.bat missing in staging — abort"
}
if (-not (Test-Path (Join-Path $stage ".env.example"))) {
    throw ".env.example missing in staging — abort"
}

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Compress-Archive -Path $stage -DestinationPath $zipPath -CompressionLevel Optimal

Remove-Item -Recurse -Force $stageRoot

$sizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host ""
Write-Host "Packed OK: $zipPath ($sizeMb MB)" -ForegroundColor Green
Write-Host "Unzip, then double-click start.bat" -ForegroundColor Green
