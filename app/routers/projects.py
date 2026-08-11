import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.services import pnl as pnl_service
from app.services.finance_pdf import build_finance_pdf
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


def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _build_timeline(project: dict, milestones: list) -> dict | None:
    """预计算甘特坐标（left%/width%）与每条里程碑的有效状态，供模板纯 CSS 渲染。"""
    today = date.today()
    anchors = []
    for m in milestones:
        s = _parse_date(m.get("start_date")) or _parse_date(m.get("end_date")) or _parse_date(m.get("due_date"))
        e = _parse_date(m.get("end_date")) or _parse_date(m.get("due_date"))
        if s:
            anchors.append(s)
        if e:
            anchors.append(e)
    ps = _parse_date(project.get("start_date"))
    pe = _parse_date(project.get("deadline"))
    if ps:
        anchors.append(ps)
    if pe:
        anchors.append(pe)
    if not anchors:
        return None

    range_start = min(anchors)
    range_end = max(anchors)
    total_days = (range_end - range_start).days
    if total_days <= 0:
        total_days = 1

    items = []
    for m in milestones:
        s = _parse_date(m.get("start_date")) or _parse_date(m.get("end_date")) or _parse_date(m.get("due_date"))
        e = _parse_date(m.get("end_date")) or _parse_date(m.get("due_date"))
        if not s:
            s = range_start
        if not e:
            e = s
        if e < s:
            e = s
        left = (s - range_start).days / total_days * 100
        width = max((e - s).days, 1) / total_days * 100
        status = m.get("status") or ""
        if not status:
            status = (
                "done"
                if m.get("done")
                else ("delayed" if (m.get("due_date") and _parse_date(m.get("due_date")) < today) else "active")
            )
        items.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "start": m.get("start_date"),
                "end": m.get("end_date") or m.get("due_date"),
                "due": m.get("due_date"),
                "status": status,
                "left_pct": round(left, 2),
                "width_pct": round(width, 2),
            }
        )

    today_offset = None
    if range_start <= today <= range_end:
        today_offset = (today - range_start).days / total_days * 100

    return {
        "start": range_start.isoformat(),
        "end": range_end.isoformat(),
        "total_days": total_days,
        "today_offset": round(today_offset, 2) if today_offset is not None else None,
        "items": items,
    }


@router.get("", response_class=HTMLResponse)
async def project_list(
    request: Request,
    user: dict = Depends(get_current_user),
    status: str = None,
    phase: str = None,
    due: str = None,
):
    """项目列表，支持 ?status=<阶段> / ?phase=active(进行中) / ?due=week 筛选（驾驶舱指标卡联动）。"""
    project_ids = get_accessible_project_ids(user)
    today = date.today()
    week_end = today + timedelta(days=7)
    conds, params = [], []
    if status:
        conds.append("p.status = ?")
        params.append(status)
    if phase == "active":
        conds.append("p.status NOT IN ('done', 'lead')")
    if due == "week":
        conds.append("p.deadline BETWEEN ? AND ? AND p.status != 'done'")
        params.extend([today.isoformat(), week_end.isoformat()])
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    with db_session() as conn:
        if project_ids is None:
            projects = rows_to_list(
                conn.execute(
                    f"""
                    SELECT p.*, c.name as client_name FROM projects p
                    LEFT JOIN clients c ON p.client_id = c.id
                    {where}
                    ORDER BY p.updated_at DESC
                    """,
                    params,
                ).fetchall()
            )
        elif project_ids:
            ph = ",".join("?" * len(project_ids))
            projects = rows_to_list(
                conn.execute(
                    f"""
                    SELECT p.*, c.name as client_name FROM projects p
                    LEFT JOIN clients c ON p.client_id = c.id
                    WHERE p.id IN ({ph}) {("AND " + " AND ".join(conds)) if conds else ""}
                    ORDER BY p.updated_at DESC
                    """,
                    list(project_ids) + params,
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
            "active_filter": {"status": status, "phase": phase, "due": due},
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
    # P0：新建项目即重算损益派生字段（此时材料/报价为空，结果为 0/NULL）
    from app.services import pnl
    pnl.recalc_project(project_id)
    log_audit(user["id"], "create", "project", project_id, name)
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=brief", status_code=303)


@router.post("/{project_id}/edit")
async def project_edit(
    project_id: int,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """更新项目基本信息."""
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403)
    form = await request.form()
    fields = {}
    for key in ("name", "status", "industry", "client_id", "area",
                "budget_min", "budget_max", "start_date", "deadline"):
        val = form.get(key)
        if val is not None and val != "":
            fields[key] = val
    # 设计师字段：允许留空以清空
    for dkey in ("lead_designer", "assistant_designer", "construction_lead"):
        if dkey in form:
            fields[dkey] = (form.get(dkey) or "")

    # type conversions
    if "client_id" in fields:
        fields["client_id"] = int(fields["client_id"]) or None
    for num_key in ("area", "budget_min", "budget_max"):
        if num_key in fields:
            fields[num_key] = float(fields[num_key])
    fields["updated_at"] = "CURRENT_TIMESTAMP"

    with db_session() as conn:
        old_row = conn.execute(
            "SELECT status, code FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        old_status = old_row[0] if old_row else ""
        old_code = old_row[1] if old_row else str(project_id)
        sets = []
        vals = []
        for k, v in fields.items():
            if k == "updated_at":
                sets.append(f"{k} = CURRENT_TIMESTAMP")
            else:
                sets.append(f"{k} = ?")
                vals.append(v)
        if sets:
            vals.append(project_id)
            conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", vals)
        # P3：阶段（status）流转时推送站内通知
        new_status = fields.get("status", old_status)
        if new_status and new_status != old_status:
            from app.services import notifications as notif

            notif.notify_stage_change(project_id, old_code, old_status, new_status)
    # P0：项目信息（含 status）变更后重算损益派生字段
    from app.services import pnl
    pnl.recalc_project(project_id)
    log_audit(user["id"], "update", "project", project_id)
    # redirect back to referring page
    redirect_url = form.get("redirect", f"/app/projects/{project_id}")
    return RedirectResponse(url=redirect_url, status_code=303)


# ── P0：损益派生字段重算端点（字段不允许客户端直写，统一由此重算落库）──────────
@router.post("/{project_id}/recalc")
async def project_recalc(project_id: int, user: dict = Depends(get_current_user)):
    """手动触发单项目损益重算（落库）。供前端/运维回填使用。"""
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403)
    from app.services import pnl

    return JSONResponse(pnl.recalc_project(project_id))


@router.post("/recalc-all")
async def project_recalc_all(user: dict = Depends(get_current_user)):
    """重算全部项目损益。仅管理员。"""
    require_admin(user)
    from app.services import pnl

    return JSONResponse({"ok": True, "recalced": pnl.recalc_all()})


@router.post("/{project_id}/milestones/add")
async def add_milestone(
    project_id: int,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """新增里程碑（含工期与状态，供甘特时间线使用）."""
    if not user_can_access_project(user, project_id) or user["role"] != "admin":
        raise HTTPException(status_code=403)
    form = await request.form()
    name = (form.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="里程碑名称不能为空")
    start_date = form.get("start_date") or None
    end_date = form.get("end_date") or None
    status = form.get("status") or "active"
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO project_milestones
                (project_id, name, start_date, end_date, due_date, status, done)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, name, start_date, end_date, end_date, status, 1 if status == "done" else 0),
        )
        mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # 里程碑自动生成一条关联任务（到期提醒）
        from app.routers.tasks import sync_task_from_milestone

        sync_task_from_milestone(
            conn, project_id,
            {"id": mid, "name": name, "end_date": end_date, "due_date": end_date},
        )
    log_audit(user["id"], "create", "milestone", project_id)
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=overview", status_code=303)


@router.post("/{project_id}/milestones/{mid}/update")
async def update_milestone(
    project_id: int,
    mid: int,
    request: Request,
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id) or user["role"] != "admin":
        raise HTTPException(status_code=403)
    form = await request.form()
    name = (form.get("name") or "").strip()
    start_date = form.get("start_date") or None
    end_date = form.get("end_date") or None
    status = form.get("status") or "active"
    with db_session() as conn:
        conn.execute(
            """
            UPDATE project_milestones
            SET name = ?, start_date = ?, end_date = ?, due_date = ?, status = ?, done = ?
            WHERE id = ? AND project_id = ?
            """,
            (name, start_date, end_date, end_date, status, 1 if status == "done" else 0, mid, project_id),
        )
        from app.routers.tasks import sync_task_from_milestone

        sync_task_from_milestone(
            conn, project_id,
            {"id": mid, "name": name, "end_date": end_date, "due_date": end_date},
        )
    log_audit(user["id"], "update", "milestone", project_id)
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=overview", status_code=303)


@router.post("/{project_id}/milestones/{mid}/delete")
async def delete_milestone(
    project_id: int,
    mid: int,
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id) or user["role"] != "admin":
        raise HTTPException(status_code=403)
    with db_session() as conn:
        from app.routers.tasks import delete_tasks_for_milestone

        delete_tasks_for_milestone(conn, mid)
        conn.execute(
            "DELETE FROM project_milestones WHERE id = ? AND project_id = ?",
            (mid, project_id),
        )
    log_audit(user["id"], "delete", "milestone", project_id)
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=overview", status_code=303)


# ---------------------------------------------------------------------------
# 施工团队：项目 ↔ 工人分配（排期 / 现场负责人）
# ---------------------------------------------------------------------------
@router.post("/{project_id}/assignments/new")
async def add_assignment(
    project_id: int,
    request: Request,
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id) or user["role"] != "admin":
        raise HTTPException(status_code=403)
    form = await request.form()
    worker_id = int(form.get("worker_id") or 0)
    if not worker_id:
        raise HTTPException(status_code=400, detail="请选择工人")
    role_on_project = (form.get("role_on_project") or "").strip()
    is_lead = 1 if form.get("is_lead") else 0
    start_date = form.get("start_date") or None
    end_date = form.get("end_date") or None
    status = (form.get("status") or "planned").strip()
    notes = (form.get("notes") or "").strip()
    with db_session() as conn:
        if is_lead:
            conn.execute(
                "UPDATE project_assignment SET is_lead = 0 WHERE project_id = ?", (project_id,)
            )
        conn.execute(
            """
            INSERT INTO project_assignment
                (project_id, worker_id, role_on_project, is_lead, start_date, end_date, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, worker_id, role_on_project or None, is_lead, start_date, end_date, status, notes or None),
        )
    log_audit(user["id"], "create", "assignment", project_id)
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=team", status_code=303)


@router.post("/{project_id}/assignments/{aid}/lead")
async def toggle_assignment_lead(
    project_id: int,
    aid: int,
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id) or user["role"] != "admin":
        raise HTTPException(status_code=403)
    with db_session() as conn:
        row = conn.execute(
            "SELECT is_lead FROM project_assignment WHERE id = ? AND project_id = ?",
            (aid, project_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        new_lead = 0 if row["is_lead"] else 1
        if new_lead:
            conn.execute(
                "UPDATE project_assignment SET is_lead = 0 WHERE project_id = ?", (project_id,)
            )
        conn.execute(
            "UPDATE project_assignment SET is_lead = ? WHERE id = ? AND project_id = ?",
            (new_lead, aid, project_id),
        )
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=team", status_code=303)


@router.post("/{project_id}/assignments/{aid}/delete")
async def delete_assignment(
    project_id: int,
    aid: int,
    user: dict = Depends(get_current_user),
):
    if not user_can_access_project(user, project_id) or user["role"] != "admin":
        raise HTTPException(status_code=403)
    with db_session() as conn:
        conn.execute(
            "DELETE FROM project_assignment WHERE id = ? AND project_id = ?",
            (aid, project_id),
        )
    log_audit(user["id"], "delete", "assignment", project_id)
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=team", status_code=303)


# ── P2 离线模板闭环（置于 /{project_id} 通配路由之前，避免被其吞掉）──────────
@router.get("/template.xlsx")
async def project_template_xlsx(user: dict = Depends(get_current_user)):
    """下载项目批量导入模板（openpyxl 生成，离线可用，含工种下拉/金额公式/条件格式）。"""
    from app.services.import_projects import build_template_bytes

    data = build_template_bytes(get_studio_defaults())
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="project_import_template.xlsx"'},
    )


@router.get("/import")
async def project_import_page(request: Request, user: dict = Depends(get_current_user)):
    """批量导入项目页面：上传 → 预览（异常行高亮）→ 确认。"""
    return templates.TemplateResponse(
        "app/projects/import.html", {"request": request, "user": user}
    )


@router.post("/import-preview")
async def project_import_preview(
    file: UploadFile = File(...), user: dict = Depends(get_current_user)
):
    """解析上传的 xlsx，返回 {rows, summary}，异常行带 errors 标记。"""
    from app.services.import_projects import parse_template_bytes

    content = await file.read()
    if not content:
        return JSONResponse({"ok": False, "error": "空文件"}, status_code=400)
    if not (file.filename or "").endswith((".xlsx", ".xlsm")):
        return JSONResponse({"ok": False, "error": "仅支持 .xlsx 模板文件"}, status_code=400)
    try:
        result = parse_template_bytes(content)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"解析失败：{exc}"}, status_code=400)
    return JSONResponse({"ok": True, **result})


@router.post("/import-confirm")
async def project_import_confirm(request: Request, user: dict = Depends(get_current_user)):
    """按预览结果批量建项目（及首条材料行），触发 P0 损益重算。"""
    from app.services import pnl as _pnl

    body = await request.json()
    rows = body.get("rows", [])
    created = []
    with db_session() as conn:
        for row in rows:
            if not row.get("ok"):
                continue
            client_id = None
            client_name = (row.get("client") or "").strip()
            if client_name:
                cid = conn.execute(
                    "SELECT id FROM clients WHERE name=?", (client_name,)
                ).fetchone()
                client_id = cid[0] if cid else None
            count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            code = f"p-{date.today().year}-{count + 1:03d}"
            conn.execute(
                "INSERT INTO projects (code, name, client_id, industry, area, status) "
                "VALUES (?,?,?,?,?,?)",
                (
                    code,
                    row["name"],
                    client_id,
                    row.get("industry") or "",
                    row.get("area"),
                    row.get("status", "lead"),
                ),
            )
            pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            qty = row.get("qty")
            price = row.get("price")
            labor = (row.get("labor") or "").strip()
            if qty and price and labor:
                conn.execute(
                    "INSERT INTO project_material (project_id, name, quantity, unit_price, status, category) "
                    "VALUES (?,?,?,?,?,?)",
                    (pid, labor, qty, price, "pending", "导入"),
                )
            created.append(pid)
    for pid in created:
        _pnl.recalc_project(pid)
    log_audit(user["id"], "import", "project", len(created), f"批量导入 {len(created)} 个项目")
    return JSONResponse({"ok": True, "created": len(created), "project_ids": created})


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
        clients = rows_to_list(conn.execute("SELECT * FROM clients ORDER BY name").fetchall())
        workers = rows_to_list(conn.execute("SELECT * FROM worker ORDER BY name").fetchall())
        assignments = rows_to_list(
            conn.execute(
                """
                SELECT a.*, w.name as worker_name, w.role as worker_role,
                       w.phone as worker_phone, w.status as worker_status
                FROM project_assignment a
                JOIN worker w ON a.worker_id = w.id
                WHERE a.project_id = ?
                ORDER BY a.is_lead DESC, w.name
                """,
                (project_id,),
            ).fetchall()
        )

    timeline = _build_timeline(project, milestones)

    show_finance = user["role"] == "admin"
    finance_pnl = None
    milestone_curve = []
    if show_finance:
        finance_pnl = pnl_service.get_pnl(project_id)
        milestone_curve = pnl_service.get_milestone_curve(project_id)
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
            "timeline": timeline,
            "feedback": feedback,
            "quotes": quotes,
            "active_quote": active_quote,
            "boq_templates": templates_list,
            "invoices": invoices if show_finance else [],
            "collaborators": collaborators if show_finance else [],
            "clients": clients,
            "defaults": defaults,
            "status_labels": STATUS_LABELS,
            "show_finance": show_finance,
            "finance_pnl": finance_pnl,
            "milestone_curve": milestone_curve,
            "workers": workers,
            "assignments": assignments,
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


# ---------------------------------------------------------------------------
# 发票管理
# ---------------------------------------------------------------------------
@router.post("/{project_id}/invoices/add")
async def add_invoice(
    project_id: int,
    type: str = Form(...),
    amount: float = Form(...),
    due_date: str = Form(""),
    invoice_number: str = Form(""),
    user: dict = Depends(require_admin),
):
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403)
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO invoices (project_id, type, amount, due_date, invoice_number)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, type, amount, due_date or None, invoice_number or None),
        )
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=finance", status_code=303)


@router.post("/{project_id}/invoices/{invoice_id}/delete")
async def delete_invoice(
    project_id: int,
    invoice_id: int,
    user: dict = Depends(require_admin),
):
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403)
    with db_session() as conn:
        conn.execute(
            "DELETE FROM invoices WHERE id = ? AND project_id = ?",
            (invoice_id, project_id),
        )
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=finance", status_code=303)


@router.post("/{project_id}/invoices/{invoice_id}/toggle")
async def toggle_invoice(
    project_id: int,
    invoice_id: int,
    user: dict = Depends(require_admin),
):
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403)
    with db_session() as conn:
        row = conn.execute(
            "SELECT paid FROM invoices WHERE id = ? AND project_id = ?",
            (invoice_id, project_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        new_paid = 0 if row["paid"] else 1
        conn.execute(
            "UPDATE invoices SET paid = ?, paid_at = ? WHERE id = ?",
            (new_paid, "CURRENT_TIMESTAMP" if new_paid else None, invoice_id),
        )
    return RedirectResponse(url=f"/app/projects/{project_id}?tab=finance", status_code=303)


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


@router.post("/{project_id}/quote/new-space")
async def create_space_quote(
    project_id: int,
    user: dict = Depends(get_current_user),
):
    """创建空间分区报价（空白起步，可后续添加空间和项目）."""
    if not user_can_access_project(user, project_id) or user["role"] == "viewer":
        raise HTTPException(status_code=403)

    defaults = get_studio_defaults()
    structure = {"mode": "spaces", "spaces": []}

    totals = calculate_quote_totals(
        structure,
        defaults["design_fee_pct"],
        defaults["management_fee_pct"],
        defaults["tax_pct"],
        defaults["margin_pct"],
    )
    with db_session() as conn:
        version = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM quotes WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO quotes (project_id, version, template_id, json_detail,
                                direct_cost, design_fee_pct, management_fee_pct,
                                tax_pct, margin_pct, total)
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                version,
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


@router.post("/{project_id}/quote/{quote_id}/update-space")
async def update_space_quote(
    project_id: int,
    quote_id: int,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """更新空间分区报价 — 前端提交 JSON 字符串."""
    if not user_can_access_project(user, project_id) or user["role"] == "viewer":
        raise HTTPException(status_code=403)

    form = await request.form()
    spaces_json = form.get("spaces_json", "[]")
    design_fee_pct = float(form.get("design_fee_pct", 0) or 0)
    management_fee_pct = float(form.get("management_fee_pct", 0) or 0)
    tax_pct = float(form.get("tax_pct", 0) or 0)
    margin_pct = float(form.get("margin_pct", 0) or 0)

    try:
        parsed = json.loads(spaces_json)
        # 前端可能提交 {mode, spaces} 或直接 [space, ...]
        if isinstance(parsed, dict) and "spaces" in parsed:
            spaces = parsed["spaces"]
        elif isinstance(parsed, list):
            spaces = parsed
        else:
            spaces = []
    except (json.JSONDecodeError, TypeError):
        spaces = []

    detail = {"mode": "spaces", "spaces": spaces}

    with db_session() as conn:
        quote = row_to_dict(
            conn.execute("SELECT * FROM quotes WHERE id = ? AND project_id = ?", (quote_id, project_id)).fetchone()
        )
        if not quote:
            raise HTTPException(status_code=404)

        totals = calculate_quote_totals(
            detail,
            design_fee_pct,
            management_fee_pct,
            tax_pct,
            margin_pct,
        )
        conn.execute(
            """
            UPDATE quotes SET json_detail = ?, direct_cost = ?, total = ?,
                design_fee_pct = ?, management_fee_pct = ?, tax_pct = ?, margin_pct = ?
            WHERE id = ?
            """,
            (
                json.dumps(detail, ensure_ascii=False),
                totals["direct_cost"],
                totals["total"],
                design_fee_pct,
                management_fee_pct,
                tax_pct,
                margin_pct,
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


@router.get("/{project_id}/quote/{quote_id}/preview", response_class=HTMLResponse)
async def quote_preview(
    project_id: int,
    quote_id: int,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """HTML 报价预览 — 打印友好."""
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403)

    project = _get_project_or_404(project_id)
    with db_session() as conn:
        quote = row_to_dict(
            conn.execute("SELECT * FROM quotes WHERE id = ? AND project_id = ?", (quote_id, project_id)).fetchone()
        )
        studio = row_to_dict(conn.execute("SELECT * FROM studio_profile WHERE id = 1").fetchone())
        client = None
        if project.get("client_id"):
            client = row_to_dict(
                conn.execute("SELECT * FROM clients WHERE id = ?", (project["client_id"],)).fetchone()
            )

    if not quote:
        raise HTTPException(status_code=404)

    detail = json.loads(quote["json_detail"]) if isinstance(quote["json_detail"], str) else quote["json_detail"]
    # 确保数量和小计已计算
    totals = calculate_quote_totals(
        detail,
        quote["design_fee_pct"],
        quote["management_fee_pct"],
        quote["tax_pct"],
        quote["margin_pct"],
    )

    return templates.TemplateResponse(
        "app/projects/quote_preview.html",
        {
            "request": request,
            "user": user,
            "project": project,
            "quote": quote,
            "detail": detail,
            "totals": totals,
            "studio": studio or {},
            "client": client or {},
        },
    )


@router.get("/{project_id}/finance.pdf")
async def export_finance_pdf(
    project_id: int,
    user: dict = Depends(require_admin),
):
    """导出项目损益报表 PDF（A4 横向）。仅 admin。"""
    if not user_can_access_project(user, project_id):
        raise HTTPException(status_code=403, detail="无权访问")
    project = _get_project_or_404(project_id)
    pnl = pnl_service.get_pnl(project_id)
    curve = pnl_service.get_milestone_curve(project_id)
    pdf_bytes = build_finance_pdf(project, pnl, curve, get_studio_defaults())
    filename = f"PnL-{project.get('code') or project_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


