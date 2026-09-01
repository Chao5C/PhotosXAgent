# PhotosXAgent development startup
# Usage:
#   .\start_dev.ps1              # docker + backend + frontend (current terminal)
#   .\start_dev.ps1 backend
#   .\start_dev.ps1 frontend
#   .\start_dev.ps1 docker
#   .\start_dev.ps1 -Install     # also reinstall Python deps

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "backend", "frontend", "docker")]
    [string]$Target = "all",
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
if (-not $Root) {
    $Root = Split-Path -Parent $MyInvocation.MyCommand.Path
}
Set-Location $Root

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"

function Test-ListenPort([int]$Port) {
    $escaped = [regex]::Escape(":$Port")
    return [bool](netstat -ano | Select-String -Pattern "LISTENING" | Select-String -Pattern "$escaped\s")
}

function Start-Infra {
    Write-Host "Starting MongoDB / Redis..." -ForegroundColor Cyan
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
        docker-compose up -d
    } else {
        docker compose up -d
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed. Is Docker Desktop running?"
    }
}

function Get-VenvPython {
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        Write-Host "Creating virtualenv .venv ..." -ForegroundColor Cyan
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "python -m venv failed" }
        return @{ Path = $python; Created = $true }
    }
    return @{ Path = $python; Created = $false }
}

function Install-PythonDeps([string]$PythonExe) {
    Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
    & $PythonExe -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw "pip install -e . failed" }
}

function Test-PythonReady([string]$PythonExe) {
    & $PythonExe -c "import fastapi, uvicorn, app.main" 2>$null
    return $LASTEXITCODE -eq 0
}

function Stop-ProcessTree([int]$ProcessId) {
    & taskkill.exe /PID $ProcessId /T /F 2>$null | Out-Null
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PhotosXAgent Development Mode" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$envExample = Join-Path $Root ".env.example"
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Write-Host "Copying .env.example -> .env ..." -ForegroundColor Cyan
    Copy-Item $envExample $envFile
    Write-Host "Edit .env to add LLM API keys for full features." -ForegroundColor Yellow
}

if ($Target -eq "docker" -or $Target -eq "all") {
    Start-Infra
}

$procs = @()

try {
    if ($Target -eq "backend" -or $Target -eq "all") {
        $venv = Get-VenvPython
        $pythonExe = $venv.Path
        $needInstall = $Install -or $venv.Created -or -not (Test-PythonReady $pythonExe)
        if ($needInstall) {
            Install-PythonDeps $pythonExe
        } else {
            Write-Host "[OK] Python deps already installed (use -Install to refresh)" -ForegroundColor Green
        }

        if (Test-ListenPort 8000) {
            Write-Host "[WARN] Port 8000 already in use, skip backend" -ForegroundColor Yellow
        } else {
            Write-Host "[1/2] Starting backend  http://localhost:8000" -ForegroundColor Yellow
            $procs += Start-Process -FilePath $pythonExe -ArgumentList @(
                "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"
            ) -WorkingDirectory $Root -NoNewWindow -PassThru
        }
    }

    if ($Target -eq "frontend" -or $Target -eq "all") {
        $frontendDir = Join-Path $Root "frontend"
        if (-not (Test-Path (Join-Path $frontendDir "package.json"))) {
            throw "frontend/package.json not found"
        }
        if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
            Write-Host "Installing frontend dependencies..." -ForegroundColor Cyan
            Push-Location $frontendDir
            try { npm install } finally { Pop-Location }
            if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
        }

        if (Test-ListenPort 3000) {
            Write-Host "[WARN] Port 3000 already in use, skip frontend" -ForegroundColor Yellow
        } else {
            Write-Host "[2/2] Starting frontend http://localhost:3000" -ForegroundColor Yellow
            $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
            if (-not $npmCmd) { $npmCmd = Get-Command npm }
            $procs += Start-Process -FilePath $npmCmd.Source -ArgumentList "run", "dev" -WorkingDirectory $frontendDir -NoNewWindow -PassThru
        }
    }

    Write-Host ""
    Write-Host "PhotosXAgent: frontend http://localhost:3000  backend http://localhost:8000" -ForegroundColor Green

    if ($procs.Count -eq 0) {
        return
    }

    Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
    Write-Host ""
    Wait-Process -Id ($procs.Id)
}
finally {
    foreach ($proc in $procs) {
        if ($proc -and -not $proc.HasExited) {
            Write-Host "Stopping PID $($proc.Id)..." -ForegroundColor Gray
            Stop-ProcessTree $proc.Id
        }
    }
}
