param(
    [string]$Token = "dev-token",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not $env:HEALTH_API_TOKEN) { $env:HEALTH_API_TOKEN = $Token }
if (-not $env:CHAT_BASE_URL) { $env:CHAT_BASE_URL = "http://127.0.0.1:8080" }
if (-not $env:CHAT_MULTI_TURN) { $env:CHAT_MULTI_TURN = "0" }

Write-Host "API:      http://${HostAddress}:${Port}/"
Write-Host "Docs:     http://${HostAddress}:${Port}/docs"
Write-Host "Token:    $env:HEALTH_API_TOKEN"
Write-Host "Dashboard dev server (separate terminal): cd dashboard; npm.cmd start"

python -m uvicorn app.main:app --host $HostAddress --port $Port --reload