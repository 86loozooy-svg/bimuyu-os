import json
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.auth import get_accessible_project_ids, get_current_user, log_audit, require_admin, user_can_access_project
from app.config import BASE_DIR
from app.database import db_session, row_to_dict, rows_to_list
from app.services.quote_engine import (
    calculate_quote_totals,
    export_quote_excel,
    export_quote_pdf,
    export_quote_word,
    get_studio_defaults,
)

router = APIRouter(prefix="/app/projects", tags=["projects"])
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


def _get_project_or_404(project_id: int) -> dict:
    with db_session() as conn:
        project = row_to_dict(
            conn.execute(
                """
                SELECT p.*, c.name as client_name FROM projects p
                LEFT JOIN clients c ON p.client_id = c.id WHERE p.id = ?
                """,
                (project_id,),
            ).fetchone()
        )
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("", response_class=HTMLResponse)
async def project_list(request: Request, user: dict = Depends(get_current_user)):
    project_ids = get_accessible_project_ids(user)
    with db_session() as conn:
        if project_ids is None:
            projects = rows_to_list(
                conn.execute(
                    """
                    SELECT p.*, c.name as client_name FROM projects p
                    LEFT JOIN clients c ON p.client_id = c.id
                    ORDER BY p.updated_at DESC
                    """
                ).fetchall()
            )
        elif project_ids:
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
        else:
            projects = []
        clients = rows_to_list(conn.execute("SELECT * FROM clients ORDER BY name").fetchall())

    return templates.TemplateResponse(
        "app/projects/list.html",
        {
            "request": request,
            "user": user,
            "projects": projects,
            "clients": clients,
            "status_labels": STATUS_LABELS,
        },
    )


@router.post("/new")
async def project_create(
    user: dict = Depends(get_current_user),
    name: str = Form(...),
    client_id: int = Form(0),
    industry: str = Form(""),
    area: float = Form(0),
    status: str = Form("lead"),
):
    with db_session() as conn:
        count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        code = f"p-{date.today().year}-{count + 1:03d}"
        conn.execute(
            """
            INSERT INTO projects (code, name, client_id, industry, area, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (code, name, client_id or None, industry, area or None, status),
        )
        project_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    log_audit(user["id"], "create", "project", project_id, name)
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=brief", status_code=303)


@router.get("/{project_id}", response_class=HTMLResponse)
async def project_detail(
    request: Request,
    project_id: int,
    tab: str = "overview",
    quote_id: int | None = None,
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403, detail="无权访问")

    project = _get_project_or_404(project_id)
    defaults = get_studio_defaults()

    with db_session() as conn:
        milestones = rows_to_list(
            conn.execute(
                "SELECT * FROM project_milestones WHERE project_id = ? ORDER BY due_date",
                (project_id,),
            ).fetchall()
        )
        feedback = rows_to_list(
            conn.execute(
                "SELECT * FROM feedback_log WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        )
        quotes = rows_to_list(
            conn.execute(
                "SELECT q.*, t.name as template_name FROM quotes q "
                "LEFT JOIN boq_templates t ON q.template_id = t.id "
                "WHERE q.project_id = ? ORDER BY q.version DESC",
                (project_id,),
            ).fetchall()
        )
        templates_list = rows_to_list(conn.execute("SELECT * FROM boq_templates").fetchall())
        invoices = rows_to_list(
            conn.execute(
                "SELECT * FROM invoices WHERE project_id = ? ORDER BY due_date",
                (project_id,),
            ).fetchall()
        )
        collaborators = rows_to_list(
            conn.execute(
                "SELECT id, email, display_name, role, project_ids FROM collaborators WHERE revoked = 0"
            ).fetchall()
        )

    show_finance = user["role"] == "admin"
    if user["role"] == "viewer":
        for q in quotes:
            q["total"] = None

    for q in quotes:
        if isinstance(q.get("json_detail"), str):
            q["parsed_detail"] = json.loads(q["json_detail"])
        else:
            q["parsed_detail"] = q.get("json_detail") or {"groups": []}

    active_quote = None
    if quote_id:
        active_quote = next((q for q in quotes if q["id"] == quote_id), None)
    elif quotes:
        active_quote = quotes[0]

    return templates.TemplateResponse(
        "app/projects/detail.html",
        {
            "request": request,
            "user": user,
            "project": project,
            "tab": tab,
            "milestones": milestones,
            "feedback": feedback,
            "quotes": quotes,
            "active_quote": active_quote,
            "boq_templates": templates_list,
            "invoices": invoices if show_finance else [],
            "collaborators": collaborators if show_finance else [],
            "defaults": defaults,
            "status_labels": STATUS_LABELS,
            "show_finance": show_finance,
        },
    )


@router.post("/{project_id}/brief")
async def save_brief(
    project_id: int,
    brief_md: str = Form(""),
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403)
    with db_session() as conn:
        conn.execute(
            "UPDATE projects SET brief_md = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (brief_md, project_id),
        )
    log_audit(user["id"], "update", "project_brief", project_id)
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=brief", status_code=303)


@router.post("/{project_id}/feedback")
async def add_feedback(
    project_id: int,
    raw_input: str = Form(...),
    category: str = Form("free"),
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403)
    with db_session() as conn:
        conn.execute(
            "INSERT INTO feedback_log (project_id, raw_input, category) VALUES (?, ?, ?)",
            (project_id, raw_input, category),
        )
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=execution", status_code=303)


@router.post("/{project_id}/quote/new")
async def create_quote(
    project_id: int,
    template_id: int = Form(...),
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id) or user["role"] == "viewer":
        raise HTTPException(status_code=403)

    defaults = get_studio_defaults()
    with db_session() as conn:
        template = row_to_dict(
            conn.execute("SELECT * FROM boq_templates WHERE id = ?", (template_id,)).fetchone()
        )
        if not template:
            raise HTTPException(status_code=404)
        structure = json.loads(template["json_structure"])
        for group in structure.get("groups", []):
            for item in group.get("items", []):
                item["quantity"] = 0

        totals = calculate_quote_totals(
            structure,
            defaults["design_fee_pct"],
            defaults["management_fee_pct"],
            defaults["tax_pct"],
            defaults["margin_pct"],
        )
        version = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM quotes WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO quotes (project_id, version, template_id, json_detail,
                                direct_cost, design_fee_pct, management_fee_pct,
                                tax_pct, margin_pct, total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                version,
                template_id,
                json.dumps(structure, ensure_ascii=False),
                totals["direct_cost"],
                defaults["design_fee_pct"],
                defaults["management_fee_pct"],
                defaults["tax_pct"],
                defaults["margin_pct"],
                totals["total"],
            ),
        )
        quote_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    return RedirectResponse(
        url=f"/app/projects/{project_id}?tab=quote&quote_id={quote_id}",
        status_code=303,
    )


@router.post("/{project_id}/quote/{quote_id}/update")
async def update_quote(
    project_id: int,
    quote_id: int,
    request: Request,
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id) or user["role"] == "viewer":
        raise HTTPException(status_code=403)

    form = await request.form()
    with db_session() as conn:
        quote = row_to_dict(
            conn.execute("SELECT * FROM quotes WHERE id = ? AND project_id = ?", (quote_id, project_id)).fetchone()
        )
        if not quote:
            raise HTTPException(status_code=404)

        detail = json.loads(quote["json_detail"])
        for gi, group_data in enumerate(detail.get("groups", [])):
            for ii, item in enumerate(group_data.get("items", [])):
                key = f"qty_{gi}_{ii}"
                item["quantity"] = float(form.get(key, 0) or 0)

        totals = calculate_quote_totals(
            detail,
            quote["design_fee_pct"],
            quote["management_fee_pct"],
            quote["tax_pct"],
            quote["margin_pct"],
        )
        conn.execute(
            """
            UPDATE quotes SET json_detail = ?, direct_cost = ?, total = ?
            WHERE id = ?
            """,
            (
                json.dumps(detail, ensure_ascii=False),
                totals["direct_cost"],
                totals["total"],
                quote_id,
            ),
        )

    return RedirectResponse(
        url=f"/app/projects/{project_id}?tab=quote&quote_id={quote_id}",
        status_code=303,
    )


@router.get("/{project_id}/quote/{quote_id}/pdf")
async def quote_pdf(project_id: int, quote_id: int, user: dict = Depends(get_current_user)):
    if not user_can_access_project(user, project_id) or user["role"] == "viewer":
        raise HTTPException(status_code=403)

    project = _get_project_or_404(project_id)
    with db_session() as conn:
        quote = row_to_dict(
            conn.execute("SELECT * FROM quotes WHERE id = ? AND project_id = ?", (quote_id, project_id)).fetchone()
        )
        studio = row_to_dict(conn.execute("SELECT * FROM studio_profile WHERE id = 1").fetchone())

    if not quote:
        raise HTTPException(status_code=404)

    pdf_bytes = export_quote_pdf(quote, project, studio or {})
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="quote-{project["code"]}-v{quote["version"]}.pdf"'},
    )


@router.get("/{project_id}/quote/{quote_id}/excel")
async def quote_excel(project_id: int, quote_id: int, user: dict = Depends(get_current_user)):
    if not user_can_access_project(user, project_id) or user["role"] == "viewer":
        raise HTTPException(status_code=403)

    project = _get_project_or_404(project_id)
    with db_session() as conn:
        quote = row_to_dict(
            conn.execute("SELECT * FROM quotes WHERE id = ? AND project_id = ?", (quote_id, project_id)).fetchone()
        )
        studio = row_to_dict(conn.execute("SELECT * FROM studio_profile WHERE id = 1").fetchone())

    if not quote:
        raise HTTPException(status_code=404)

    excel_bytes = export_quote_excel(quote, project, studio or {})
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="quote-{project["code"]}-v{quote["version"]}.xlsx"'},
    )


@router.get("/{project_id}/quote/{quote_id}/word")
async def quote_word(project_id: int, quote_id: int, user: dict = Depends(get_current_user)):
    if not user_can_access_project(user, project_id) or user["role"] == "viewer":
        raise HTTPException(status_code=403)

    project = _get_project_or_404(project_id)
    with db_session() as conn:
        quote = row_to_dict(
            conn.execute("SELECT * FROM quotes WHERE id = ? AND project_id = ?", (quote_id, project_id)).fetchone()
        )
        studio = row_to_dict(conn.execute("SELECT * FROM studio_profile WHERE id = 1").fetchone())

    if not quote:
        raise HTTPException(status_code=404)

    word_bytes = export_quote_word(quote, project, studio or {})
    return Response(
        content=word_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="quote-{project["code"]}-v{quote["version"]}.docx"'},
    )
