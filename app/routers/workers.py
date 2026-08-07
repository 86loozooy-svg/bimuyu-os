"""工人通讯录：全局工人档案 CRUD（姓名/工种/电话 tel: 链接/微信/工价等）。"""

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, log_audit, require_admin
from app.config import BASE_DIR
from app.database import db_session, row_to_dict, rows_to_list

router = APIRouter(prefix="/app/workers", tags=["workers"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

ROLE_OPTIONS = ["项目经理", "设计师", "木工", "油漆工", "水电工", "电工", "安装工", "瓦工", "监理", "其他"]
STATUS_OPTIONS = ["active", "inactive"]


@router.get("", response_class=HTMLResponse)
async def workers_page(
    request: Request,
    edit: int = Query(0),
    user: dict = Depends(require_admin),
):
    with db_session() as conn:
        workers = rows_to_list(
            conn.execute("SELECT * FROM worker ORDER BY status, name").fetchall()
        )
        edit_worker = None
        if edit:
            edit_worker = row_to_dict(
                conn.execute("SELECT * FROM worker WHERE id = ?", (edit,)).fetchone()
            )
    return templates.TemplateResponse(
        "app/workers.html",
        {
            "request": request,
            "user": user,
            "workers": workers,
            "edit_worker": edit_worker,
            "role_options": ROLE_OPTIONS,
            "status_options": STATUS_OPTIONS,
        },
    )


@router.post("/new")
async def create_worker(
    user: dict = Depends(require_admin),
    name: str = Form(...),
    role: str = Form(""),
    phone: str = Form(""),
    wechat: str = Form(""),
    id_number: str = Form(""),
    daily_rate: float = Form(0),
    company: str = Form(""),
    status: str = Form("active"),
    notes: str = Form(""),
):
    name = (name or "").strip()
    if not name:
        return RedirectResponse(url="/app/workers", status_code=303)
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO worker (name, role, phone, wechat, id_number, daily_rate,
                                company, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                role or None,
                phone or None,
                wechat or None,
                id_number or None,
                daily_rate or 0,
                company or None,
                status or "active",
                notes or None,
            ),
        )
        wid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    log_audit(user["id"], "create", "worker", wid, name)
    return RedirectResponse(url="/app/workers", status_code=303)


@router.post("/{worker_id}/edit")
async def edit_worker(
    worker_id: int,
    user: dict = Depends(require_admin),
    name: str = Form(...),
    role: str = Form(""),
    phone: str = Form(""),
    wechat: str = Form(""),
    id_number: str = Form(""),
    daily_rate: float = Form(0),
    company: str = Form(""),
    status: str = Form("active"),
    notes: str = Form(""),
):
    name = (name or "").strip()
    if not name:
        return RedirectResponse(url=f"/app/workers?edit={worker_id}", status_code=303)
    with db_session() as conn:
        conn.execute(
            """
            UPDATE worker SET name=?, role=?, phone=?, wechat=?, id_number=?,
                daily_rate=?, company=?, status=?, notes=?
            WHERE id=?
            """,
            (
                name,
                role or None,
                phone or None,
                wechat or None,
                id_number or None,
                daily_rate or 0,
                company or None,
                status or "active",
                notes or None,
                worker_id,
            ),
        )
    log_audit(user["id"], "update", "worker", worker_id, name)
    return RedirectResponse(url="/app/workers", status_code=303)


@router.post("/{worker_id}/delete")
async def delete_worker(worker_id: int, user: dict = Depends(require_admin)):
    with db_session() as conn:
        # 解除其项目分配
        conn.execute("DELETE FROM project_assignment WHERE worker_id = ?", (worker_id,))
        conn.execute("DELETE FROM worker WHERE id = ?", (worker_id,))
    log_audit(user["id"], "delete", "worker", worker_id)
    return RedirectResponse(url="/app/workers", status_code=303)
