param(
    [switch]$SkipTests,
    [switch]$SkipAudit,
    [switch]$Fast,
    [switch]$IncludeOptionalTests
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

function Invoke-PytestBatch {
    param(
        [string]$Name,
        [string[]]$Paths
    )

    Invoke-Step $Name {
        & $Python -m pytest @Paths --tb=short -q
    }
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
        Invoke-PytestBatch "Pytest socle API/metier" @(
            "tests/test_advanced_security.py",
            "tests/test_alembic_migrations.py",
            "tests/test_api_cmu.py",
            "tests/test_audit_compliance.py",
            "tests/test_auth_hardening.py",
            "tests/test_auth_refresh.py",
            "tests/test_auto_validation.py",
            "tests/test_billing_engine.py",
            "tests/test_bnpl_tracker.py",
            "tests/test_bulk_import.py"
        )

        Invoke-PytestBatch "Pytest cockpit/resultats/referentiels" @(
            "tests/test_api.py",
            "tests/test_api_sensitive.py",
            "tests/test_notifications.py",
            "tests/test_critical_notifier.py",
            "tests/test_code_mapping.py",
            "tests/test_cockpit_template.py",
            "tests/test_bioref.py"
        )

        Invoke-PytestBatch "Pytest analyses/FHIR/prescriptions" @(
            "tests/test_critical_ranges.py",
            "tests/test_delta_check.py",
            "tests/test_epidemiology.py",
            "tests/test_equipment_maintenance.py",
            "tests/test_exam_catalog_and_parser.py",
            "tests/test_expiry_and_amend.py",
            "tests/test_fhir_export.py",
            "tests/test_fhir_pharmacy.py",
            "tests/test_login_security.py",
            "tests/test_malaria_mobilenetv2.py",
            "tests/test_med_logic.py",
            "tests/test_migrations_integrity.py",
            "tests/test_notifications.py",
            "tests/test_onmci_client.py",
            "tests/test_patient_history.py",
            "tests/test_pdf_prescription.py",
            "tests/test_phase3_performance.py",
            "tests/test_precis_expert.py",
            "tests/test_prescription_scanner.py"
        )

        Invoke-PytestBatch "Pytest qualite/stock/securite/services" @(
            "tests/test_qc.py",
            "tests/test_quality_nc_capa.py",
            "tests/test_rate_limiting.py",
            "tests/test_rbac_and_compliance_trend.py",
            "tests/test_redis_fanout_and_patient_update.py",
            "tests/test_reference_ranges.py",
            "tests/test_registre_import_analytics.py",
            "tests/test_security.py",
            "tests/test_security_hardening.py",
            "tests/test_seed_demo.py",
            "tests/test_stock_notifications.py",
            "tests/test_stock_predictor.py",
            "tests/test_tat_tracking.py",
            "tests/test_token_cleanup.py",
            "tests/test_token_revocation.py",
            "tests/test_unit_services.py"
        )

        if ($IncludeOptionalTests) {
            Invoke-PytestBatch "Pytest optionnels ML" @(
                "tests/test_ml_pipeline.py",
                "tests/test_security.py"
            )
        } else {
            Write-Host ""
            Write-Host "Tests optionnels ML ignores par defaut (utiliser -IncludeOptionalTests)." -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "Validation terminee." -ForegroundColor Green
