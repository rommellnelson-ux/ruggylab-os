param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

Write-Host "RuggyLab OS - Installation Windows" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python est introuvable. Installe Python 3.13+ puis relance ce script."
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creation de l'environnement virtuel .venv"
    python -m venv .venv
} else {
    Write-Host "Environnement virtuel deja present"
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Pip = Join-Path $Root ".venv\Scripts\pip.exe"
$Alembic = Join-Path $Root ".venv\Scripts\alembic.exe"

Write-Host "Installation des dependances"
& $Python -m pip install --upgrade pip
& $Pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Host "Creation du fichier .env depuis .env.example"
    Copy-Item ".env.example" ".env"
    Write-Host "IMPORTANT: modifie SECRET_KEY et FIRST_SUPERUSER_PASSWORD dans .env avant un usage reel." -ForegroundColor Yellow
} elseif ($Force) {
    Write-Host "Option -Force: .env existe deja, il n'est pas remplace automatiquement." -ForegroundColor Yellow
} else {
    Write-Host "Fichier .env deja present"
}

New-Item -ItemType Directory -Force -Path "data", "data\microscopy", "backups", "models", "logs" | Out-Null

Write-Host "Application des migrations"
& $Alembic upgrade head

Write-Host ""
Write-Host "Installation terminee." -ForegroundColor Green
Write-Host "Demarrage: .\scripts\start.ps1"
Write-Host "Application: http://127.0.0.1:8000/app"
Write-Host "Swagger:     http://127.0.0.1:8000/docs"
