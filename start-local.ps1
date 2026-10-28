$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create environment first: python -m venv .venv'
}
& $pythonPath -m uvicorn BE.main:app --host 127.0.0.1 --port 8000
