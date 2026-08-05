from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, log_audit, require_admin
from app.config import BASE_DIR
from app.database import db_session, rows_to_list

router = APIRouter(prefix="/app/library", tags=["library"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("", response_class=HTMLResponse)
async def library_index(request: Request, user: dict = Depends(get_current_user)):
    with db_session() as conn:
        materials = rows_to_list(conn.execute("SELECT * FROM materials ORDER BY category, name").fetchall())
        labor = rows_to_list(conn.execute("SELECT * FROM labor_items ORDER BY name").fetchall())
        boq_templates = rows_to_list(conn.execute("SELECT * FROM boq_templates ORDER BY name").fetchall())

    return templates.TemplateResponse(
        "app/library/index.html",
        {
            "request": request,
            "user": user,
            "materials": materials,
            "labor": labor,
            "boq_templates": boq_templates,
        },
    )


@router.post("/materials/new")
async def add_material(
    user: dict = Depends(require_admin),
    name: str = Form(...),
    brand: str = Form(""),
    spec: str = Form(""),
    unit: str = Form(""),
    ref_price: float = Form(0),
    supplier: str = Form(""),
    category: str = Form("其他"),
):
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO materials (name, brand, spec, unit, ref_price, supplier, category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, brand, spec, unit, ref_price, supplier, category),
        )
        mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    log_audit(user["id"], "create", "material", mid, name)
    return RedirectResponse(url="/app/library?tab=materials", status_code=303)


@router.post("/materials/{material_id}/delete")
async def delete_material(material_id: int, user: dict = Depends(require_admin)):
    with db_session() as conn:
        conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    log_audit(user["id"], "delete", "material", material_id)
    return RedirectResponse(url="/app/library?tab=materials", status_code=303)


@router.post("/labor/new")
async def add_labor(
    user: dict = Depends(require_admin),
    name: str = Form(...),
    unit: str = Form("工日"),
    day_rate: float = Form(0),
    skill_level: str = Form("中级"),
):
    with db_session() as conn:
        conn.execute(
            "INSERT INTO labor_items (name, unit, day_rate, skill_level) VALUES (?, ?, ?, ?)",
            (name, unit, day_rate, skill_level),
        )
        lid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    log_audit(user["id"], "create", "labor", lid, name)
    return RedirectResponse(url="/app/library?tab=labor", status_code=303)


@router.post("/labor/{labor_id}/delete")
async def delete_labor(labor_id: int, user: dict = Depends(require_admin)):
    with db_session() as conn:
        conn.execute("DELETE FROM labor_items WHERE id = ?", (labor_id,))
    log_audit(user["id"], "delete", "labor", labor_id)
    return RedirectResponse(url="/app/library?tab=labor", status_code=303)
