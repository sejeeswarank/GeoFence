[CmdletBinding()]
param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "No virtual environment found at .venv" -ForegroundColor Yellow
    Write-Host "Run .\setup.ps1 first." -ForegroundColor Yellow
    exit 1
}

$uvicornArgs = @("-m", "uvicorn", "main:app", "--host", $HostAddress, "--port", "$Port")
if (-not $NoReload) {
    $uvicornArgs += "--reload"
}

Write-Host "Starting GeoFence Vision on http://localhost:$Port ..." -ForegroundColor Cyan
& $venvPython @uvicornArgs
