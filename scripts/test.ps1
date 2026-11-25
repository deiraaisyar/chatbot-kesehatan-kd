$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host "Python backend tests..."
python -m unittest discover -s tests -v

Write-Host "Dashboard contract tests..."
Push-Location (Join-Path $repo "dashboard")
try {
    node --test test/contract.test.js
} finally {
    Pop-Location
}