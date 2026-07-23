<#
.SYNOPSIS
    Restauration PostgreSQL VÉRIFIÉE sur base vierge — RuggyLab OS (§28).

.DESCRIPTION
    Implémente la restauration automatisée vérifiée exigée par les Instructions maîtres §28 :
      1. préparer une base vierge (scratch) ;
      2. restaurer le dump ;
      3. vérifier le schéma (tables présentes) ;
      4. vérifier Alembic (head attendu) ;
      5. vérifier les comptes (table users non vide) ;
      6. vérifier les volumes métier (patients/results/...) ;
      7. lancer un smoke test (requête de jointure) ;
      8. produire un rapport.

    Une sauvegarde n'est considérée VÉRIFIÉE qu'après succès de ce script.
    La base scratch est supprimée en fin d'exécution (sauf -Keep). La base de
    PRODUCTION n'est jamais touchée.

.PARAMETER BackupFile
    Chemin du dump à vérifier (.dump ou .dump.enc). Si .enc, $env:BACKUP_PASSPHRASE requis.

.PARAMETER ExpectedHead
    Révision Alembic attendue (défaut: 20260723_0038 — à maintenir aligné sur le
    head réel du dépôt à chaque nouvelle migration).

.PARAMETER ScratchDb
    Nom de la base temporaire de vérification (défaut: ruggylab_verify).

.PARAMETER Keep
    Conserve la base scratch après vérification (pour inspection manuelle).

.EXAMPLE
    ./scripts/pg_restore_verify.ps1 -BackupFile backups/ruggylab_pg-20260625-020000.dump
#>
param(
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [string]$ExpectedHead = "20260723_0038",
    [string]$ScratchDb = "ruggylab_verify",
    [string]$ComposeService = "postgres",
    [switch]$Keep
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

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
$PgDb = Get-EnvValue "POSTGRES_DB" "ruggylab"

function Assert-SafeScratchDatabase(
    [string]$DatabaseName,
    [string]$ProductionDatabase
) {
    if ($DatabaseName -notmatch '^ruggylab_verify(?:_[a-z0-9]+)?$') {
        throw "Nom de base scratch refusé : utiliser ruggylab_verify ou ruggylab_verify_<suffixe>."
    }
    $ProtectedDatabases = @("postgres", "template0", "template1", $ProductionDatabase)
    if ($ProtectedDatabases -contains $DatabaseName) {
        throw "Base scratch refusée : '$DatabaseName' est une base protégée."
    }
}

# Cette garde précède toute commande DROP/CREATE et interdit de cibler la base
# configurée de l'application ou une base système.
Assert-SafeScratchDatabase $ScratchDb $PgDb

# Helper : exécute du SQL dans la base scratch et renvoie une valeur scalaire (-tA).
function Invoke-Psql([string]$Sql, [string]$Db = $ScratchDb) {
    $out = & docker compose exec -T $ComposeService psql -U $PgUser -d $Db -tA -c $Sql
    if ($LASTEXITCODE -ne 0) { throw "psql a échoué : $Sql" }
    return ($out | Out-String).Trim()
}

# ── Rapport ───────────────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path "artifacts" | Out-Null
$Stamp      = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportPath = Join-Path "artifacts" "restore-verify-$Stamp.txt"
$Report = [System.Collections.Generic.List[string]]::new()
$Failed = $false
$ScratchCreated = $false
function Step([string]$Name, [bool]$Ok, [string]$Detail) {
    $tag = if ($Ok) { "PASS" } else { "FAIL"; }
    $line = "[{0}] {1} — {2}" -f $tag, $Name, $Detail
    $Report.Add($line)
    $color = if ($Ok) { "Green" } else { "Red" }
    Write-Host $line -ForegroundColor $color
    if (-not $Ok) { $script:Failed = $true }
}

$Report.Add("RuggyLab OS — Rapport de restauration vérifiée (§28)")
$Report.Add("Date    : $(Get-Date -Format o)")
$Report.Add("Dump    : $BackupFile")
$Report.Add("Scratch : $ScratchDb")
$Report.Add("Head attendu : $ExpectedHead")
$Report.Add("".PadRight(60, '-'))

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "docker introuvable : la vérification s'exécute via docker compose."
    }
    if (-not (Test-Path $BackupFile)) { throw "Dump introuvable : $BackupFile" }

    # ── 0. Contrôle d'intégrité (SHA-256) ─────────────────────────────────────
    $shaSidecar = "$BackupFile.sha256"
    if (Test-Path $shaSidecar) {
        $expected = (Get-Content $shaSidecar -Raw).Split(' ')[0].Trim()
        $actual = (Get-FileHash -Algorithm SHA256 -Path $BackupFile).Hash
        Step "Intégrité SHA-256" ($expected -ieq $actual) "attendu=$expected actuel=$actual"
        if ($Failed) { throw "Empreinte SHA-256 non concordante — dump corrompu." }
    } else {
        Step "Intégrité SHA-256" $false "Empreinte SHA-256 absente : sidecar requis."
        throw "Empreinte SHA-256 absente — sauvegarde non vérifiable."
    }

    # ── Déchiffrement éventuel ─────────────────────────────────────────────────
    $RestoreSource = $BackupFile
    $TempPlain = $null
    if ($BackupFile.EndsWith(".enc")) {
        if ([string]::IsNullOrWhiteSpace($env:BACKUP_PASSPHRASE)) { throw "Dump chiffré : \$env:BACKUP_PASSPHRASE requis." }
        $TempPlain = Join-Path $env:TEMP "ruggylab-restore-$Stamp.dump"
        & openssl enc -d -aes-256-cbc -pbkdf2 -in $BackupFile -out $TempPlain -pass env:BACKUP_PASSPHRASE
        if ($LASTEXITCODE -ne 0) { throw "Déchiffrement openssl a échoué." }
        $RestoreSource = $TempPlain
    }

    # ── 1. Base vierge ────────────────────────────────────────────────────────
    & docker compose exec -T $ComposeService psql -U $PgUser -d postgres -c "DROP DATABASE IF EXISTS $ScratchDb;" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Suppression de l'ancienne base scratch échouée." }
    & docker compose exec -T $ComposeService psql -U $PgUser -d postgres -c "CREATE DATABASE $ScratchDb;" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Création de la base scratch échouée." }
    $ScratchCreated = $true
    Step "Base vierge préparée" $true "DATABASE $ScratchDb créée"

    # ── 2. Restauration ───────────────────────────────────────────────────────
    # Copie du dump dans le conteneur (binaire fiable), puis pg_restore depuis le fichier.
    $InContainer = "/tmp/ruggylab-restore-$Stamp.dump"
    & docker compose cp $RestoreSource "${ComposeService}:$InContainer"
    if ($LASTEXITCODE -ne 0) { throw "Copie du dump dans le conteneur échouée." }
    & docker compose exec -T $ComposeService pg_restore -U $PgUser -d $ScratchDb --no-owner --no-privileges --exit-on-error $InContainer
    $RestoreExitCode = $LASTEXITCODE
    & docker compose exec -T $ComposeService rm -f $InContainer | Out-Null
    if ($RestoreExitCode -ne 0) { throw "pg_restore a échoué (code $RestoreExitCode)." }
    Step "Restauration pg_restore" $true "dump appliqué (validation par contrôles ci-dessous)"

    # ── 3. Schéma ──────────────────────────────────────────────────────────────
    $tableCount = [int](Invoke-Psql "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
    Step "Schéma (tables public)" ($tableCount -ge 20) "$tableCount tables (seuil 20)"

    # ── 4. Alembic ─────────────────────────────────────────────────────────────
    $head = Invoke-Psql "SELECT version_num FROM alembic_version LIMIT 1;"
    Step "Head Alembic" ($head -eq $ExpectedHead) "trouvé=$head attendu=$ExpectedHead"

    # ── 5. Comptes ─────────────────────────────────────────────────────────────
    $userCount = [int](Invoke-Psql "SELECT count(*) FROM users;")
    Step "Comptes (users)" ($userCount -ge 1) "$userCount compte(s)"

    # ── 6. Volumes métier ──────────────────────────────────────────────────────
    foreach ($t in @("patients", "exam_orders", "results", "invoices", "audit_events")) {
        $c = Invoke-Psql "SELECT count(*) FROM $t;"
        Step "Volume $t" $true "$c ligne(s)"
    }

    # ── 7. Smoke test (jointure représentative) ───────────────────────────────
    $smoke = Invoke-Psql "SELECT count(*) FROM exam_orders o LEFT JOIN patients p ON p.id = o.patient_id;"
    Step "Smoke test (jointure orders/patients)" $true "$smoke ligne(s) jointes"

} catch {
    Step "Exception" $false $_.Exception.Message
} finally {
    # ── Nettoyage ──────────────────────────────────────────────────────────────
    if ($TempPlain -and (Test-Path $TempPlain)) { Remove-Item $TempPlain -Force }
    if ($ScratchCreated -and -not $Keep) {
        try {
            & docker compose exec -T $ComposeService psql -U $PgUser -d postgres -c "DROP DATABASE IF EXISTS $ScratchDb;" | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "DROP DATABASE a échoué." }
            $Report.Add("[INFO] Base scratch $ScratchDb supprimée.")
        } catch { $Report.Add("[WARN] Échec suppression base scratch : $($_.Exception.Message)") }
    } elseif ($ScratchCreated) {
        $Report.Add("[INFO] Base scratch $ScratchDb conservée (-Keep).")
    } else {
        $Report.Add("[INFO] Aucune base scratch créée par cette exécution.")
    }

    $Report.Add("".PadRight(60, '-'))
    $verdict = if ($Failed) { "ÉCHEC — sauvegarde NON vérifiée" } else { "SUCCÈS — sauvegarde VÉRIFIÉE" }
    $Report.Add("VERDICT : $verdict")
    $Report | Set-Content -Path $ReportPath -Encoding UTF8
    Write-Host ""
    Write-Host "Rapport écrit : $ReportPath" -ForegroundColor Cyan
    $verdictColor = if ($Failed) { "Red" } else { "Green" }
    Write-Host "VERDICT : $verdict" -ForegroundColor $verdictColor
}

if ($Failed) { exit 1 } else { exit 0 }
