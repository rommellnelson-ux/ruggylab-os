param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$DatabasePath = "ruggylab_os.db"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Test-Path $BackupPath)) {
    throw "Sauvegarde introuvable: $BackupPath"
}

if (Test-Path $DatabasePath) {
    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $SafetyCopy = "$DatabasePath.before-restore-$Stamp"
    Copy-Item $DatabasePath $SafetyCopy
    Write-Host "Copie de securite creee: $SafetyCopy" -ForegroundColor Yellow
}

Copy-Item $BackupPath $DatabasePath -Force
Write-Host "Base restauree depuis: $BackupPath" -ForegroundColor Green
