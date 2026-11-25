$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$dashboard = Join-Path $repo "dashboard"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js 20+ is required to build the dashboard."
}

Push-Location $dashboard
try {
    npm.cmd run build
} finally {
    Pop-Location
}
Write-Host "Dashboard build copied to dashboard/dist."