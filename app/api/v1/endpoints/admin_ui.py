from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.api.deps import require_admin


router = APIRouter(prefix="/admin")


@router.get("/ratios", response_class=HTMLResponse)
def ratios_admin_ui(_: None = Depends(require_admin)) -> str:
    template_path = Path(__file__).resolve().parents[3] / "templates" / "admin_ratios.html"
    return template_path.read_text(encoding="utf-8")
