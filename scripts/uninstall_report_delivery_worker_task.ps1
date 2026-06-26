<#
.SYNOPSIS
    Desinstalle la tache planifiee RuggyLab Report Delivery Outbox Worker.
#>
param(
    [string]$TaskName = "RuggyLab Report Delivery Outbox Worker"
)

$ErrorActionPreference = "Stop"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Tache supprimee: $TaskName" -ForegroundColor Green
} else {
    Write-Host "Tache absente: $TaskName" -ForegroundColor Yellow
}
