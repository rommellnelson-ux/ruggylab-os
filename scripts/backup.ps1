param(
    [string]$DatabasePath = "ruggylab_os.db"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path $DatabasePath)) {
    throw "Base SQLite introuvable: $DatabasePath"
}

New-Item -ItemType Directory -Force -Path "backups" | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupPath = Join-Path "backups" "ruggylab_os-$Stamp.db"
Copy-Item $DatabasePath $BackupPath

Write-Host "Sauvegarde creee: $BackupPath" -ForegroundColor Green
