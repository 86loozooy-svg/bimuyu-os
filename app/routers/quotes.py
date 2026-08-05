from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_accessible_project_ids, get_current_user
from app.config import BASE_DIR
from app.database import db_session, rows_to_list

router = APIRouter(prefix="/app/quotes", tags=["quotes"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("", response_class=HTMLResponse)
async def quotes_list(request: Request, user: dict = Depends(get_current_user)):
    project_ids = get_accessible_project_ids(user)
    with db_session() as conn:
        if project_ids is None:
            quotes = rows_to_list(
                conn.execute(
                    """
                    SELECT q.*, p.name as project_name, p.code as project_code,
                           t.name as template_name
                    FROM quotes q
                    JOIN projects p ON q.project_id = p.id
                    LEFT JOIN boq_templates t ON q.template_id = t.id
                    ORDER BY q.created_at DESC
                    """
                ).fetchall()
            )
        elif project_ids:
            placeholders = ",".join("?" * len(project_ids))
            quotes = rows_to_list(
                conn.execute(
                    f"""
                    SELECT q.*, p.name as project_name, p.code as project_code,
                           t.name as template_name
                    FROM quotes q
                    JOIN projects p ON q.project_id = p.id
                    LEFT JOIN boq_templates t ON q.template_id = t.id
                    WHERE q.project_id IN ({placeholders})
                    ORDER BY q.created_at DESC
                    """,
                    project_ids,
                ).fetchall()
            )
        else:
            quotes = []

    if user["role"] == "viewer":
        for q in quotes:
            q["total"] = None

    return templates.TemplateResponse(
        "app/quotes/index.html",
        {"request": request, "user": user, "quotes": quotes},
    )
