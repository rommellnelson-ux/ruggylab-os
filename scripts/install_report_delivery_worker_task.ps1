<#
.SYNOPSIS
    Installe la tache planifiee RuggyLab Report Delivery Outbox Worker.

.DESCRIPTION
    Execute regulierement scripts/process_report_delivery_outbox.py pour traiter
    les comptes-rendus a diffuser. La tache tourne sous l'utilisateur courant et
    s'appuie sur la venv locale du projet.

.EXAMPLE
    .\scripts\install_report_delivery_worker_task.ps1
    .\scripts\install_report_delivery_worker_task.ps1 -IntervalMinutes 2 -Limit 100
#>
param(
    [string]$TaskName = "RuggyLab Report Delivery Outbox Worker",
    [int]$IntervalMinutes = 5,
    [int]$Limit = 50,
    [int]$MaxAttempts = 8,
    [int]$RepetitionDays = 3650
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\process_report_delivery_outbox.py"

if (-not (Test-Path $Python)) {
    throw "Python introuvable: $Python. Creez la venv puis relancez scripts\install.ps1."
}
if (-not (Test-Path $Script)) {
    throw "Worker introuvable: $Script"
}

$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "`"$Script`" --once --limit $Limit --max-attempts $MaxAttempts" `
    -WorkingDirectory $Root

$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days $RepetitionDays)

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Traite la file outbox de diffusion des comptes-rendus RuggyLab OS." `
    -Force `
    -ErrorAction Stop | Out-Null

Write-Host "Tache installee: $TaskName" -ForegroundColor Green
Write-Host "Frequence: toutes les $IntervalMinutes minutes. Limite par passage: $Limit."
Write-Host "Duree de repetition: $RepetitionDays jours."
