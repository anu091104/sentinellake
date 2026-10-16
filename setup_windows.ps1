# SentinelLake - one-step Windows setup (laptop mode).
#
# Run from a normal PowerShell window (not inside VS Code), in this folder:
#     powershell -ExecutionPolicy Bypass -File setup_windows.ps1
#
# It creates ONE virtual environment (.venv) in this folder, installs the
# packages, and runs the environment check including a real Spark start.

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
Write-Host ""
Write-Host "SentinelLake setup in $PSScriptRoot" -ForegroundColor Cyan

if ($PSScriptRoot -match " ") {
    Write-Host "This folder path contains a space. Move the project to a path without spaces, e.g. D:\sentinellake" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $PSScriptRoot "tasks.py"))) {
    Write-Host "tasks.py not found here. Run this script from the project folder (the one with README.md)." -ForegroundColor Red
    exit 1
}

# 1. Python 3.12
$pyver = (& py -3.12 --version) 2>$null
if ($LASTEXITCODE -ne 0 -or -not ($pyver -match "3\.12")) {
    Write-Host "Python 3.12 was not found. Install 'Python 3.12 Windows installer (64-bit)' from python.org, then run this again." -ForegroundColor Red
    exit 1
}
Write-Host "[ok] $pyver"

# 2. One fresh virtual environment
if (Test-Path .venv) {
    Write-Host "Removing the old .venv ..."
    Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
    if (Test-Path .venv) {
        Write-Host "Could not delete .venv (a program is using it). Close VS Code, or restart the laptop, then run this again." -ForegroundColor Red
        exit 1
    }
}
Write-Host "Creating .venv with Python 3.12 ..."
& py -3.12 -m venv .venv
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "Creating the virtual environment failed." -ForegroundColor Red; exit 1 }

# 3. Packages (3-5 minutes; leave the window alone)
Write-Host "Installing packages (3-5 minutes, please do not press any key) ..."
& $py -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "Package install failed - see the error above." -ForegroundColor Red; exit 1 }

# 4. Check everything, including starting Spark once
& $py tasks.py doctor
Write-Host ""
Write-Host "From now on, run tasks with:  .\sl doctor   .\sl test   .\sl demo" -ForegroundColor Cyan
