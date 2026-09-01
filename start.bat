@echo off
chcp 65001 >nul
cd /d "%~dp0"
title PhotosXAgent One-Click Start

echo.
echo ========================================
echo   PhotosXAgent One-Click Deploy / Start
echo ========================================
echo.

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker not found. Install and start Docker Desktop first.
  pause
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found. Install Node.js 18+ and add to PATH.
  pause
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    echo [INFO] No .env found, copying from .env.example ...
    copy /Y ".env.example" ".env" >nul
    echo [TIP] Edit .env and set LLM API keys for full features.
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_dev.ps1" all
if errorlevel 1 (
  echo.
  echo [ERROR] Startup failed. See logs above.
  pause
  exit /b 1
)

pause
