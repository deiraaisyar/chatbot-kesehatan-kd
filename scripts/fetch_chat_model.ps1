param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Destination) {
    $Destination = Join-Path $repo "models\chat\0.5B-q4_k_m.gguf"
}
$Destination = [IO.Path]::GetFullPath($Destination)
$url = "https://huggingface.co/naiiaiai/chatbot-kesehatan-qwen2.5-0.5b/resolve/main/gguf/0.5B-q4_k_m.gguf?download=true"
$expected = "4117c4248a581dafcf020fd1c1b5fb84826e92236a6c12c37db2a665e0448490"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null

if (Test-Path -LiteralPath $Destination) {
    $existing = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($existing -eq $expected) {
        Write-Host "Model already present and verified: $Destination"
        exit 0
    }
    Write-Host "Existing file has the wrong checksum; downloading a fresh copy."
    Remove-Item -LiteralPath $Destination -Force
}

Write-Host "Downloading the Qwen2.5-0.5B Q4_K_M GGUF (~380 MiB)..."
if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
    & curl.exe -L --fail --retry 3 --output $Destination $url
} else {
    Invoke-WebRequest -Uri $url -OutFile $Destination
}

$actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    Remove-Item -LiteralPath $Destination -Force
    throw "Checksum mismatch. Expected $expected, got $actual."
}
Write-Host "Saved and verified: $Destination"