from fastapi import APIRouter

from app.api.v1.endpoints.audit_events import router as audit_events_router
from app.api.v1.endpoints.admin_ui import router as admin_ui_router
from app.api.v1.endpoints.equipments import router as equipments_router
from app.api.v1.endpoints.equipment_reagent_ratios import router as equipment_reagent_ratios_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.imaging import router as imaging_router
from app.api.v1.endpoints.login import router as login_router
from app.api.v1.endpoints.operations import router as operations_router
from app.api.v1.endpoints.patients import router as patients_router
from app.api.v1.endpoints.reagents import router as reagents_router
from app.api.v1.endpoints.ratio_presets import router as ratio_presets_router
from app.api.v1.endpoints.reports import router as reports_router
from app.api.v1.endpoints.results import router as results_router
from app.api.v1.endpoints.results_poct import router as results_poct_router
from app.api.v1.endpoints.samples import router as samples_router
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
api_router.include_router(equipments_router, tags=["equipments"])
api_router.include_router(samples_router, tags=["samples"])
api_router.include_router(results_router, tags=["results"])
api_router.include_router(results_poct_router, tags=["poct"])
api_router.include_router(imaging_router, tags=["imaging"])
api_router.include_router(operations_router, tags=["operations"])
api_router.include_router(reports_router, tags=["reports"])
