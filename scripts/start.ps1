param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Alembic = Join-Path $Root ".venv\Scripts\alembic.exe"

if (-not (Test-Path $Python)) {
    throw "Environnement .venv introuvable. Lance d'abord .\scripts\install.ps1"
}

if (-not (Test-Path ".env")) {
    throw "Fichier .env introuvable. Lance d'abord .\scripts\install.ps1"
}

Write-Host "Application des migrations"
& $Alembic upgrade head

Write-Host ""
Write-Host "RuggyLab OS demarre sur:" -ForegroundColor Cyan
Write-Host "Application: http://$HostAddress`:$Port/app"
Write-Host "Swagger:     http://$HostAddress`:$Port/docs"
Write-Host ""

$ArgsList = @("-m", "uvicorn", "app.main:app", "--host", $HostAddress, "--port", "$Port")
if ($Reload) {
    $ArgsList += "--reload"
}

& $Python @ArgsList
