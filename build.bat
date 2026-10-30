@echo off
REM ==============================================================================
REM QuantClaw Build Script
REM ==============================================================================
REM
REM Compiles the QuantClaw application into a standalone Windows .exe
REM
REM Prerequisites:
REM   1. Python 3.11+ installed
REM   2. pip install -r requirements.txt
REM   3. PyInstaller installed (included in requirements.txt)
REM
REM Output: dist\QuantClaw.exe
REM
REM ==============================================================================

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║         QUANTCLAW BUILD SYSTEM v1.0.0           ║
echo  ║      AI-Assisted Algorithmic Trading App        ║
echo  ╚══════════════════════════════════════════════════╝
echo.

REM ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

echo [1/4] Python found:
python --version
echo.

REM ── Install Dependencies ─────────────────────────────────────────────────────
echo [2/4] Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo       Done.
echo.

REM ── Clean Previous Build ─────────────────────────────────────────────────────
echo [3/4] Cleaning previous build artifacts...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
echo       Done.
echo.

REM ── Build with PyInstaller ───────────────────────────────────────────────────
echo [4/4] Building QuantClaw.exe with PyInstaller...
echo       This may take 2-5 minutes...
echo.
python -m PyInstaller quantclaw.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check the output above for errors.
    pause
    exit /b 1
)

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║           BUILD SUCCESSFUL!                     ║
echo  ║                                                 ║
echo  ║   Output: dist\QuantClaw.exe                    ║
echo  ║                                                 ║
echo  ║   Run it:                                       ║
echo  ║     dist\QuantClaw.exe                          ║
echo  ║                                                 ║
echo  ║   Or for development:                           ║
echo  ║     python -m quantclaw.main                    ║
echo  ╚══════════════════════════════════════════════════╝
echo.

pause
