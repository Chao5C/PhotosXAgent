param(
    [ValidateSet("all", "backend", "frontend", "docker")]
    [string]$Target = "all"
)

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($Target -eq "docker" -or $Target -eq "all") {
    Write-Host "Starting MongoDB / Redis..." -ForegroundColor Cyan
    docker-compose up -d
}

if ($Target -eq "backend" -or $Target -eq "all") {
    if (-not (Test-Path ".venv")) {
        python -m venv .venv
    }
    & "$Root\.venv\Scripts\Activate.ps1"
    pip install -e . -q
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
}

if ($Target -eq "frontend" -or $Target -eq "all") {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root\frontend'; if (-not (Test-Path node_modules)) { npm install }; npm run dev"
}

Write-Host "PhotosXAgent: frontend http://localhost:3000  backend http://localhost:8000" -ForegroundColor Green
