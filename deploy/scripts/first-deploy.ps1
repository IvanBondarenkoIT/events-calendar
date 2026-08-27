param(
    [string]$DeployDir = "",
    [string]$Image = "ghcr.io/ivanbondarenkoit/events-calendar:latest",
    [switch]$SkipLogin
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DeployDir)) {
    $DeployDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

New-Item -ItemType Directory -Force -Path (Join-Path $DeployDir "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DeployDir "logs") | Out-Null

$envFile = Join-Path $DeployDir ".env"
if (!(Test-Path -LiteralPath $envFile)) {
    $example = Join-Path $DeployDir ".env.example"
    if (Test-Path -LiteralPath $example) {
        Copy-Item $example $envFile
        Write-Host "Created $envFile from .env.example — FILL SECRETS before jobs."
    }
    else {
        throw "Missing .env and .env.example in $DeployDir"
    }
}

if (-not $SkipLogin) {
    Write-Host "docker login ghcr.io (use GitHub username + PAT with read:packages)"
    docker login ghcr.io
}

Write-Host "Pulling $Image ..."
docker pull $Image

Write-Host "Smoke: check-config"
docker run --rm --env-file $envFile `
    -e TZ=Asia/Tbilisi -e PYTHONPATH=/app/src `
    -v "$(Join-Path $DeployDir 'data'):/app/data" `
    $Image python -m dec_calendar check-config

Write-Host "Smoke: check-jira (needs filled JIRA_* in .env)"
docker run --rm --env-file $envFile `
    -e TZ=Asia/Tbilisi -e PYTHONPATH=/app/src `
    -v "$(Join-Path $DeployDir 'data'):/app/data" `
    $Image python -m dec_calendar check-jira

Write-Host "Next: install scheduled tasks:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$DeployDir\deploy\scripts\install-scheduled-tasks.ps1`" -DeployDir `"$DeployDir`""
Write-Host "Or if scripts copied to scripts\:"
Write-Host "  powershell -ExecutionPolicy Bypass -File `"$DeployDir\scripts\install-scheduled-tasks.ps1`" -DeployDir `"$DeployDir`""
