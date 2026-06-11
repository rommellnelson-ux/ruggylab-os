from fastapi import APIRouter

from app.api.v1.endpoints.admin_ui import router as admin_ui_router
from app.api.v1.endpoints.audit_events import router as audit_events_router
from app.api.v1.endpoints.auto_validation import router as auto_validation_router
from app.api.v1.endpoints.bioref import router as bioref_router
from app.api.v1.endpoints.billing import router as billing_router
from app.api.v1.endpoints.bnpl import router as bnpl_router
from app.api.v1.endpoints.bulk_import import router as bulk_import_router
from app.api.v1.endpoints.critical_alerts import router as critical_alerts_router
from app.api.v1.endpoints.critical_ranges import router as critical_ranges_router
from app.api.v1.endpoints.delta_check import router as delta_check_router
from app.api.v1.endpoints.dh36 import router as dh36_router
from app.api.v1.endpoints.epidemiology import router as epidemiology_router
from app.api.v1.endpoints.equipment_maintenance import router as equipment_maintenance_router
from app.api.v1.endpoints.equipment_reagent_ratios import (
    router as equipment_reagent_ratios_router,
)
from app.api.v1.endpoints.equipments import router as equipments_router
from app.api.v1.endpoints.fhir_pharmacy import router as fhir_pharmacy_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.imaging import router as imaging_router
from app.api.v1.endpoints.login import router as login_router
from app.api.v1.endpoints.maintenance import router as maintenance_router
from app.api.v1.endpoints.military_facilities import router as military_facilities_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.operations import router as operations_router
from app.api.v1.endpoints.patients import router as patients_router
from app.api.v1.endpoints.pdf_prescription import router as pdf_prescription_router
from app.api.v1.endpoints.prescription_scanner import router as prescription_scanner_router
from app.api.v1.endpoints.qc import router as qc_router
from app.api.v1.endpoints.quality import router as quality_router
from app.api.v1.endpoints.ratio_presets import router as ratio_presets_router
from app.api.v1.endpoints.reagents import router as reagents_router
from app.api.v1.endpoints.reference_ranges import router as reference_ranges_router
from app.api.v1.endpoints.registre import router as registre_router
from app.api.v1.endpoints.reports import router as reports_router
from app.api.v1.endpoints.results import router as results_router
from app.api.v1.endpoints.results_poct import router as results_poct_router
from app.api.v1.endpoints.samples import router as samples_router
from app.api.v1.endpoints.stats import router as stats_router
from app.api.v1.endpoints.stock_notifications import router as stock_notifications_router
from app.api.v1.endpoints.stock_predictor import router as stock_predictor_router
from app.api.v1.endpoints.tat import router as tat_router
from app.api.v1.endpoints.users import router as users_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(admin_ui_router, tags=["admin-ui"])
api_router.include_router(login_router, tags=["auth"])
api_router.include_router(users_router, tags=["users"])
api_router.include_router(reagents_router, tags=["reagents"])
api_router.include_router(equipment_reagent_ratios_router, tags=["equipment-reagent-ratios"])
api_router.include_router(ratio_presets_router, tags=["ratio-presets"])
api_router.include_router(audit_events_router, tags=["audit-events"])
api_router.include_router(patients_router, tags=["patients"])
api_router.include_router(qc_router, tags=["QC Analytique"])
api_router.include_router(critical_ranges_router, tags=["Critical Ranges"])
api_router.include_router(delta_check_router, tags=["Delta-Check"])
api_router.include_router(reference_ranges_router, tags=["Reference Ranges"])
api_router.include_router(critical_alerts_router, tags=["Critical Alerts"])
api_router.include_router(equipments_router, tags=["equipments"])
api_router.include_router(equipment_maintenance_router, tags=["Equipment Maintenance"])
api_router.include_router(stats_router, tags=["Lab Stats"])
api_router.include_router(samples_router, tags=["samples"])
api_router.include_router(results_router, tags=["results"])
api_router.include_router(auto_validation_router, tags=["Auto-Validation"])
api_router.include_router(results_poct_router, tags=["poct"])
api_router.include_router(military_facilities_router, tags=["military-facilities"])
api_router.include_router(dh36_router, tags=["dh36"])
api_router.include_router(imaging_router, tags=["imaging"])
api_router.include_router(operations_router, tags=["operations"])
api_router.include_router(reports_router, tags=["reports"])
api_router.include_router(maintenance_router, tags=["maintenance"])
api_router.include_router(billing_router, tags=["Billing CMU"])
api_router.include_router(stock_predictor_router, tags=["Stock Predictor CMU"])
api_router.include_router(stock_notifications_router, tags=["Stock Predictor CMU"])
api_router.include_router(prescription_scanner_router, tags=["Prescription Scanner CMU"])
api_router.include_router(pdf_prescription_router, tags=["Prescription Scanner CMU"])
api_router.include_router(fhir_pharmacy_router, tags=["FHIR R4 Pharmacy"])
api_router.include_router(epidemiology_router, tags=["Epidemiology"])
api_router.include_router(bnpl_router, tags=["BNPL CMU"])
api_router.include_router(notifications_router, tags=["Notifications temps-réel"])
api_router.include_router(bulk_import_router, tags=["Import en lot"])
api_router.include_router(quality_router, tags=["Qualité NC/CAPA"])
api_router.include_router(tat_router, tags=["Suivi TAT"])
api_router.include_router(registre_router, tags=["Registre maître"])
api_router.include_router(bioref_router, tags=["Référentiel biologique"])
