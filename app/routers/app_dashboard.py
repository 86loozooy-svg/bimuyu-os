from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_accessible_project_ids, get_current_user
from app.config import BASE_DIR
from app.database import db_session, row_to_dict, rows_to_list

router = APIRouter(prefix="/app", tags=["dashboard"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

STATUS_LABELS = {
    "lead": "线索",
    "brief": "Brief",
    "quoting": "报价中",
    "signed": "已签约",
    "designing": "设计中",
    "delivering": "交付中",
    "done": "已完成",
}


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(get_current_user)):
    today = date.today()
    week_end = today + timedelta(days=7)
    project_ids = get_accessible_project_ids(user)

    with db_session() as conn:
        if project_ids is None:
            projects = rows_to_list(
                conn.execute(
                    "SELECT p.*, c.name as client_name FROM projects p "
                    "LEFT JOIN clients c ON p.client_id = c.id "
                    "ORDER BY p.updated_at DESC"
                ).fetchall()
            )
            active_count = conn.execute(
                "SELECT COUNT(*) FROM projects WHERE status NOT IN ('done', 'lead')"
            ).fetchone()[0]
            due_this_week = conn.execute(
                "SELECT COUNT(*) FROM projects WHERE deadline BETWEEN ? AND ? AND status != 'done'",
                (today.isoformat(), week_end.isoformat()),
            ).fetchone()[0]
            pending_payment = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM invoices WHERE paid = 0"
            ).fetchone()[0]
            leads = conn.execute(
                "SELECT COUNT(*) FROM projects WHERE status = 'lead'"
            ).fetchone()[0]
        else:
            if not project_ids:
                projects = []
                active_count = due_this_week = pending_payment = leads = 0
            else:
                placeholders = ",".join("?" * len(project_ids))
                projects = rows_to_list(
                    conn.execute(
                        f"""
                        SELECT p.*, c.name as client_name FROM projects p
                        LEFT JOIN clients c ON p.client_id = c.id
                        WHERE p.id IN ({placeholders})
                        ORDER BY p.updated_at DESC
                        """,
                        project_ids,
                    ).fetchall()
                )
                active_count = sum(1 for p in projects if p["status"] not in ("done", "lead"))
                due_this_week = sum(
                    1
                    for p in projects
                    if p.get("deadline")
                    and today.isoformat() <= p["deadline"] <= week_end.isoformat()
                    and p["status"] != "done"
                )
                pending_payment = 0
                leads = sum(1 for p in projects if p["status"] == "lead")

        milestones = rows_to_list(
            conn.execute(
                """
                SELECT m.*, p.name as project_name, p.code as project_code
                FROM project_milestones m
                JOIN projects p ON m.project_id = p.id
                WHERE m.done = 0 AND m.due_date <= ?
                ORDER BY m.due_date LIMIT 10
                """,
                (week_end.isoformat(),),
            ).fetchall()
        )

        studio = row_to_dict(conn.execute("SELECT * FROM studio_profile WHERE id = 1").fetchone())

    return templates.TemplateResponse(
        "app/dashboard.html",
        {
            "request": request,
            "user": user,
            "studio": studio,
            "projects": projects,
            "milestones": milestones,
            "stats": {
                "active": active_count,
                "due_week": due_this_week,
                "pending_payment": pending_payment,
                "leads": leads,
            },
            "status_labels": STATUS_LABELS,
        },
    )


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline(request: Request, user: dict = Depends(get_current_user)):
    project_ids = get_accessible_project_ids(user)
    with db_session() as conn:
        if project_ids is None:
            projects = rows_to_list(
                conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
            )
        elif project_ids:
            placeholders = ",".join("?" * len(project_ids))
            projects = rows_to_list(
                conn.execute(
                    f"SELECT * FROM projects WHERE id IN ({placeholders}) ORDER BY updated_at DESC",
                    project_ids,
                ).fetchall()
            )
        else:
            projects = []

    columns = ["lead", "brief", "quoting", "signed", "designing", "delivering", "done"]
    board = {col: [p for p in projects if p["status"] == col] for col in columns}

    return templates.TemplateResponse(
        "app/pipeline.html",
        {
            "request": request,
            "user": user,
            "board": board,
            "status_labels": STATUS_LABELS,
        },
    )
