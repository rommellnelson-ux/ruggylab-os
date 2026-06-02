param(
    [switch]$SkipTests,
    [switch]$SkipAudit,
    [switch]$Fast
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Command
}

Write-Host "RuggyLab OS - Validation" -ForegroundColor Cyan

Invoke-Step "Ruff" {
    & $Python -m ruff check app tests
}

if (-not $SkipAudit) {
    Invoke-Step "Bandit" {
        & $Python -m bandit -q -r app -c pyproject.toml
    }

    Invoke-Step "pip-audit" {
        & $Python -m pip_audit -r requirements.txt --ignore-vuln PYSEC-2025-183
    }
}

if (-not $SkipTests) {
    if ($Fast) {
        Invoke-Step "Pytest auth/API cible" {
            & $Python -m pytest tests/test_security.py tests/test_login_security.py tests/test_auth_refresh.py tests/test_api.py --tb=short -q
        }
    } else {
        Invoke-Step "Pytest complet" {
            & $Python -m pytest --tb=short -q
        }
    }
}

Write-Host ""
Write-Host "Validation terminee." -ForegroundColor Green
