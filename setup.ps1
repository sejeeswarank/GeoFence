[CmdletBinding()]
param(
    [switch]$SkipPipUpgrade
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$requirementsFile = Join-Path $PSScriptRoot "backend\requirements.txt"

function Get-PythonRuntime {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return @{
            Executable = $pythonCmd.Source
            PrefixArgs = @()
            Label = "python"
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @{
            Executable = $pyLauncher.Source
            PrefixArgs = @("-3")
            Label = "py -3"
        }
    }

    $commonPaths = @(
        "$env:LocalAppData\Programs\Python\Python312\python.exe",
        "$env:LocalAppData\Programs\Python\Python311\python.exe",
        "$env:LocalAppData\Programs\Python\Python310\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:ProgramFiles\Python310\python.exe"
    )

    foreach ($path in $commonPaths) {
        if (Test-Path $path) {
            return @{
                Executable = $path
                PrefixArgs = @()
                Label = $path
            }
        }
    }

    return $null
}

$runtime = Get-PythonRuntime
if (-not $runtime) {
    Write-Host ""
    Write-Host "Python 3.10+ was not found." -ForegroundColor Yellow
    Write-Host "Install Python, reopen PowerShell, then run .\setup.ps1 again." -ForegroundColor Yellow
    Write-Host "Recommended download: https://www.python.org/downloads/windows/" -ForegroundColor Cyan
    exit 1
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment with $($runtime.Label)..." -ForegroundColor Cyan
    & $runtime.Executable @($runtime.PrefixArgs + @("-m", "venv", ".venv"))
}
else {
    Write-Host "Using existing virtual environment at .venv" -ForegroundColor Cyan
}

if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment creation failed." -ForegroundColor Red
    exit 1
}

if (-not $SkipPipUpgrade) {
    Write-Host "Upgrading pip..." -ForegroundColor Cyan
    & $venvPython -m pip install --upgrade pip
}

Write-Host "Installing dependencies from backend\\requirements.txt..." -ForegroundColor Cyan
& $venvPython -m pip install -r $requirementsFile

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "  1. Run .\run.ps1" -ForegroundColor Gray
Write-Host "  2. Open http://localhost:8000" -ForegroundColor Gray
Write-Host "  3. Check FIRST_RUN_CHECKLIST.md if the camera or model needs attention" -ForegroundColor Gray
