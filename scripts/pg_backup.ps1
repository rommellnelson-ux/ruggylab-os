<#
.SYNOPSIS
    Sauvegarde PostgreSQL de production (pg_dump, format custom) — RuggyLab OS.

.DESCRIPTION
    Effectue un pg_dump du service `postgres` (docker-compose) au format custom (-Fc),
    horodate le fichier, calcule une empreinte SHA-256, applique une rétention et
    écrit un marqueur de dernier succès (alimente la métrique backup_last_success_timestamp).

    Conforme aux exigences §28 (sauvegarde) des Instructions maîtres :
      - dump PostgreSQL ;
      - contrôle d'intégrité (SHA-256) ;
      - rétention ;
      - chiffrement optionnel (-Encrypt + $env:BACKUP_PASSPHRASE) ;
      - logs / marqueur de succès.

    NB : ce script remplace l'usage "production" de backup.ps1, qui ne couvre que SQLite
    (développement local). Voir docs/DEPLOYMENT.md.

.PARAMETER ComposeService
    Nom du service docker-compose PostgreSQL (défaut: postgres).

.PARAMETER RetentionDays
    Nombre de jours de rétention locale des dumps (défaut: 14). 0 = pas de purge.

.PARAMETER Encrypt
    Si présent, chiffre le dump avec openssl AES-256 (passphrase via $env:BACKUP_PASSPHRASE).

.EXAMPLE
    ./scripts/pg_backup.ps1
    ./scripts/pg_backup.ps1 -RetentionDays 30 -Encrypt
#>
param(
    [string]$ComposeService = "postgres",
    [int]$RetentionDays = 14,
    [switch]$Encrypt
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

# ── Lecture .env (POSTGRES_USER / POSTGRES_DB) ────────────────────────────────
function Get-EnvValue([string]$Key, [string]$Default) {
    if (-not (Test-Path ".env")) { return $Default }
    foreach ($line in Get-Content ".env") {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.+?)\s*$") {
            return $Matches[1].Trim('"').Trim("'")
        }
    }
    return $Default
}

$PgUser = Get-EnvValue "POSTGRES_USER" "ruggylab"
$PgDb   = Get-EnvValue "POSTGRES_DB"   "ruggylab"

# ── Préconditions ─────────────────────────────────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker introuvable : la sauvegarde PostgreSQL s'exécute via docker compose."
}
if ($Encrypt -and [string]::IsNullOrWhiteSpace($env:BACKUP_PASSPHRASE)) {
    throw "-Encrypt demandé mais \$env:BACKUP_PASSPHRASE est vide."
}
if ($RetentionDays -lt 0) {
    throw "RetentionDays doit être positif ou nul."
}
if ($Encrypt -and -not (Get-Command openssl -ErrorAction SilentlyContinue)) {
    throw "openssl introuvable : requis avec -Encrypt."
}

New-Item -ItemType Directory -Force -Path "backups" | Out-Null
$Stamp      = Get-Date -Format "yyyyMMdd-HHmmss"
$DumpName   = "ruggylab_pg-$Stamp.dump"
$DumpPath   = Join-Path "backups" $DumpName

Write-Host "Sauvegarde PostgreSQL : base '$PgDb' (user '$PgUser') via service '$ComposeService'..." -ForegroundColor Cyan

# ── pg_dump (format custom) ───────────────────────────────────────────────────
# On dumpe vers un fichier DANS le conteneur puis on le copie : streamer du
# binaire via le pipeline PowerShell corromprait le dump.
$InContainer = "/tmp/$DumpName"
& docker compose exec -T $ComposeService pg_dump -U $PgUser -d $PgDb -Fc -f $InContainer
if ($LASTEXITCODE -ne 0) { throw "pg_dump a échoué (code $LASTEXITCODE)." }
& docker compose cp "${ComposeService}:$InContainer" $DumpPath
if ($LASTEXITCODE -ne 0) {
    & docker compose exec -T $ComposeService rm -f $InContainer | Out-Null
    throw "Copie du dump hors conteneur échouée."
}
& docker compose exec -T $ComposeService pg_restore --list $InContainer | Out-Null
$listExitCode = $LASTEXITCODE
& docker compose exec -T $ComposeService rm -f $InContainer | Out-Null
if ($listExitCode -ne 0) {
    Remove-Item $DumpPath -Force -ErrorAction SilentlyContinue
    throw "Le catalogue du dump est illisible selon pg_restore --list."
}

$SizeBytes = (Get-Item $DumpPath).Length
if ($SizeBytes -lt 1024) { throw "Dump suspicieusement petit ($SizeBytes octets) — abandon." }

# ── Chiffrement optionnel ─────────────────────────────────────────────────────
if ($Encrypt) {
    $EncPath = "$DumpPath.enc"
    & openssl enc -aes-256-cbc -pbkdf2 -salt -in $DumpPath -out $EncPath -pass env:BACKUP_PASSPHRASE
    if ($LASTEXITCODE -ne 0) { throw "Chiffrement openssl a échoué." }
    Remove-Item $DumpPath -Force
    $DumpPath = $EncPath
    Write-Host "Dump chiffré (AES-256)." -ForegroundColor Green
}

# ── Empreinte d'intégrité ─────────────────────────────────────────────────────
$Hash = (Get-FileHash -Algorithm SHA256 -Path $DumpPath).Hash
"$Hash  $(Split-Path $DumpPath -Leaf)" | Set-Content -Path "$DumpPath.sha256" -Encoding ASCII

# ── Marqueur de dernier succès (métrique backup_last_success_timestamp) ───────
$Marker = @{
    last_success_utc = (Get-Date).ToUniversalTime().ToString("o")
    file             = (Split-Path $DumpPath -Leaf)
    sha256           = $Hash
    size_bytes       = (Get-Item $DumpPath).Length
    encrypted        = [bool]$Encrypt
} | ConvertTo-Json
$Marker | Set-Content -Path (Join-Path "backups" "last_success.json") -Encoding UTF8

# ── Rétention ─────────────────────────────────────────────────────────────────
if ($RetentionDays -gt 0) {
    $Cutoff = (Get-Date).AddDays(-$RetentionDays)
    Get-ChildItem "backups" -File |
        Where-Object { $_.Name -like "ruggylab_pg-*" -and $_.LastWriteTime -lt $Cutoff } |
        ForEach-Object {
            Remove-Item $_.FullName -Force
            Write-Host "Purgé (>$RetentionDays j) : $($_.Name)" -ForegroundColor DarkYellow
        }
}

Write-Host "Sauvegarde créée : $DumpPath" -ForegroundColor Green
Write-Host "  SHA-256 : $Hash" -ForegroundColor Green
Write-Host "RAPPEL §28 : copier ce dump HORS-SITE (disque chiffré / 4G) et vérifier la restauration via scripts/pg_restore_verify.ps1." -ForegroundColor Yellow
