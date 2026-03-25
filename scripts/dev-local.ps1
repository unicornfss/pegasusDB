param(
    [string]$HostName = "0.0.0.0",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "Virtual environment Python not found at $venvPython. Create it with: py -m venv .venv"
}

$address = "$HostName`:$Port"
Write-Host "Starting Django dev server at http://$address using $venvPython"
& $venvPython manage.py runserver $address
