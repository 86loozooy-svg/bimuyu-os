import json
import math
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_accessible_project_ids, get_current_user, log_audit
from app.config import BASE_DIR
from app.database import db_session, row_to_dict, rows_to_list

router = APIRouter(prefix="/app", tags=["dashboard"])
router_root = APIRouter(tags=["dashboard-root"])  # 无前缀：承载 /dashboard
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

STATUS_LABELS = {
    "lead": "线索",
    "brief": "简报",
    "quoting": "报价中",
    "signed": "已签约",
    "designing": "设计中",
    "delivering": "交付中",
    "done": "已完成",
}

LEVEL_META = {
    "owner":     ("主理人", "owner"),
    "creator":   ("主理人", "creator"),
    "developer": ("开发者", "developer"),
    "vip":       ("VIP", "vip"),
    "pro":       ("专业版", "pro"),
    "standard":  ("标准成员", "standard"),
    "member":    ("标准成员", "member"),
    "trial":     ("试用", "standard"),
}
ACTIVITY_VERBS = {
    "create":  ("创建了", "i-create", "plus"),
    "update":  ("更新了", "i-update", "pencil"),
    "delete":  ("删除了", "i-delete", "trash-2"),
    "import":  ("批量导入了", "i-create", "upload"),
    "invite":  ("邀请了", "i-invite", "user-plus"),
    "revoke":  ("移除了", "i-delete", "user-minus"),
}


def _level_info(user: dict) -> dict:
    raw = (user.get("membership_level") or "").strip().lower()
    if not raw or raw == "standard":
        raw = "owner" if user.get("role") == "admin" else "standard"
    label, cls = LEVEL_META.get(raw, ("标准成员", "standard"))
    return {"level": raw, "label": label, "cls": cls}


def _score_projects(projects, progress_map, today, max_amount, user):
    """本周重点项目加权评分：时间敏感度×0.4 + 风险×0.3 + 金额×0.2 + 角色匹配×0.1。"""
    for p in projects:
        p["progress"] = round(progress_map.get(p["id"], 0))
        dl = p.get("deadline")
        try:
            days = (date.fromisoformat(dl) - today).days if dl else 999
        except Exception:
            days = 999
        if days < 0 or days <= 7:
            ts = 1.0
        elif days <= 14:
            ts = 0.7
        elif days <= 30:
            ts = 0.4
        else:
            ts = 0.1
        if p.get("overdue"):
            risk = 1.0
        elif p["status"] in ("designing", "delivering"):
            risk = 0.6
        elif p["status"] in ("quoting", "brief"):
            risk = 0.4
        elif p["status"] == "lead":
            risk = 0.2
        else:
            risk = 0.15
        try:
            amt = float(p.get("budget_max") or p.get("budget_min") or 0)
        except (TypeError, ValueError):
            amt = 0
        money = (amt / max_amount) if max_amount else 0.1
        role_match = 1.0
        p["_score"] = round(ts * 0.4 + risk * 0.3 + money * 0.2 + role_match * 0.1, 3)
        p["_risk"] = risk
        p["_days"] = days
    return sorted(projects, key=lambda x: x["_score"], reverse=True)


def _risk_text(p):
    if p.get("overdue"):
        return ("is-bad", "⚠ 存在已逾期里程碑，请尽快跟进")
    if p["_days"] is not None and 0 <= p["_days"] <= 7:
        return ("is-bad", f"⚠ 距阶段截止仅 {p['_days']} 天")
    if p["_risk"] >= 0.6:
        return ("is-warn", "进行中项目，注意推进节奏与交付质量")
    return ("is-ok", "进展正常，按计划推进中")


def _fetch_projects(conn, project_ids):
    """按权限拉取项目 + 汇总指标。返回 (projects, active_count, due_this_week, pending_payment, leads)。"""
    today = date.today()
    week_end = today + timedelta(days=7)
    if project_ids is None:
        projects = rows_to_list(
            conn.execute(
                "SELECT p.*, c.name as client_name FROM projects p "
                "LEFT JOIN clients c ON p.client_id = c.id ORDER BY p.updated_at DESC"
            ).fetchall()
        )
        active_count = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status NOT IN ('done','lead')"
        ).fetchone()[0]
        due_this_week = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE deadline BETWEEN ? AND ? AND status != 'done'",
            (today.isoformat(), week_end.isoformat()),
        ).fetchone()[0]
        pending_payment = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM invoices WHERE paid = 0"
        ).fetchone()[0]
        leads = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status='lead'"
        ).fetchone()[0]
    elif project_ids:
        ph = ",".join("?" * len(project_ids))
        projects = rows_to_list(
            conn.execute(
                f"SELECT p.*, c.name as client_name FROM projects p "
                f"LEFT JOIN clients c ON p.client_id = c.id WHERE p.id IN ({ph}) ORDER BY p.updated_at DESC",
                project_ids,
            ).fetchall()
        )
        active_count = sum(1 for p in projects if p["status"] not in ("done", "lead"))
        due_this_week = sum(
            1 for p in projects if p.get("deadline")
            and today.isoformat() <= p["deadline"] <= week_end.isoformat()
            and p["status"] != "done"
        )
        pending_payment = 0
        leads = sum(1 for p in projects if p["status"] == "lead")
    else:
        projects = []
        active_count = due_this_week = pending_payment = leads = 0
    return projects, active_count, due_this_week, pending_payment, leads


def _compute_progress_overdue(conn, projects, today):
    """给 projects 注入 overdue 标记，返回 (progress_map, overdue_set)。"""
    prog_rows = conn.execute(
        "SELECT project_id, COUNT(*) AS total, COALESCE(SUM(done),0) AS done "
        "FROM project_milestones GROUP BY project_id"
    ).fetchall()
    progress_map = {
        r["project_id"]: (r["done"] / r["total"] * 100) if r["total"] else 0
        for r in prog_rows
    }
    overdue_rows = conn.execute(
        "SELECT DISTINCT project_id FROM project_milestones "
        "WHERE done=0 AND due_date IS NOT NULL AND due_date < ?",
        (today.isoformat(),),
    ).fetchall()
    overdue_set = {r["project_id"] for r in overdue_rows}
    for p in projects:
        p["overdue"] = p["id"] in overdue_set
    return progress_map, overdue_set


def _upcoming_milestones(conn, project_ids, today, days=7, limit=6):
    """近期待办里程碑（未完成的未来 N 天），替换原写死的假时间轴数据。"""
    end = (today + timedelta(days=days)).isoformat()
    if project_ids is None:
        rows = conn.execute(
            "SELECT m.name, m.due_date, p.name AS project_name, p.id AS project_id "
            "FROM project_milestones m JOIN projects p ON m.project_id=p.id "
            "WHERE m.done=0 AND m.due_date IS NOT NULL AND m.due_date BETWEEN ? AND ? "
            "ORDER BY m.due_date ASC LIMIT ?",
            (today.isoformat(), end, limit),
        ).fetchall()
    elif project_ids:
        ph = ",".join("?" * len(project_ids))
        rows = conn.execute(
            f"SELECT m.name, m.due_date, p.name AS project_name, p.id AS project_id "
            f"FROM project_milestones m JOIN projects p ON m.project_id=p.id "
            f"WHERE m.done=0 AND m.due_date IS NOT NULL AND m.due_date BETWEEN ? AND ? "
            f"AND m.project_id IN ({ph}) ORDER BY m.due_date ASC LIMIT ?",
            (today.isoformat(), end, *project_ids, limit),
        ).fetchall()
    else:
        rows = []
    out = []
    for r in rows:
        due = r["due_date"]
        try:
            d = date.fromisoformat(due)
            left = (d - today).days
        except Exception:
            d, left = None, 999
        color = "var(--color-error)" if left < 0 else ("var(--color-warning)" if left <= 3 else "var(--color-info)")
        label = f"{d.month}月{d.day}日" if d else (due or "")
        out.append({
            "time": label,
            "event": f"{r['project_name']} · {r['name']}",
            "color": color,
            "link": f"/app/projects/{r['project_id']}",
        })
    return out


# ───────────────────────── 重点项目持久化 ─────────────────────────
def _ensure_prefs(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS user_dashboard_prefs (
             user_id INTEGER PRIMARY KEY,
             pinned_top_project_id INTEGER,
             manual_slots TEXT,
             hidden_ids TEXT
        )"""
    )


def _get_prefs(conn, user_id: int) -> dict:
    _ensure_prefs(conn)
    row = conn.execute(
        "SELECT pinned_top_project_id, manual_slots, hidden_ids FROM user_dashboard_prefs WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if not row:
        return {"pinned_top_project_id": None, "manual_slots": [], "hidden_ids": []}
    return {
        "pinned_top_project_id": row["pinned_top_project_id"],
        "manual_slots": json.loads(row["manual_slots"]) if row["manual_slots"] else [],
        "hidden_ids": json.loads(row["hidden_ids"]) if row["hidden_ids"] else [],
    }


def _set_prefs(conn, user_id: int, **fields):
    _ensure_prefs(conn)
    cur = _get_prefs(conn, user_id)
    cur.update({k: v for k, v in fields.items() if v is not None})
    conn.execute(
        """INSERT INTO user_dashboard_prefs (user_id, pinned_top_project_id, manual_slots, hidden_ids)
           VALUES (?,?,?,?)
           ON CONFLICT(user_id) DO UPDATE SET
             pinned_top_project_id=excluded.pinned_top_project_id,
             manual_slots=excluded.manual_slots,
             hidden_ids=excluded.hidden_ids""",
        (
            user_id,
            cur["pinned_top_project_id"],
            json.dumps(cur["manual_slots"]),
            json.dumps(cur["hidden_ids"]),
        ),
    )


def _project_subtasks(conn, project_id: int):
    """TOP1 三条子任务进度条：按里程碑顺序分 3 组算完成率，三态色。"""
    rows = conn.execute(
        "SELECT name, done FROM project_milestones WHERE project_id=? ORDER BY id",
        (project_id,),
    ).fetchall()
    ms = [dict(r) for r in rows]
    n = len(ms)
    if n == 0:
        return []
    size = max(1, math.ceil(n / 3))
    names = ["设计", "施工", "验收"]
    out = []
    for i in range(3):
        g = ms[i * size:(i + 1) * size]
        if not g:
            continue
        done = sum(1 for x in g if x["done"])
        pct = round(done / len(g) * 100)
        tone = "is-ok" if pct >= 85 else ("is-warn" if pct >= 45 else "is-bad")
        out.append({"name": names[i], "pct": pct, "tone": tone})
    return out


def _serialize_kp(p, conn, is_top1: bool, pinned: bool):
    try:
        amt = float(p.get("budget_max") or p.get("budget_min") or 0)
    except (TypeError, ValueError):
        amt = 0
    d = {
        "id": p["id"],
        "name": p["name"],
        "code": p.get("code") or "",
        "client_name": p.get("client_name") or "未指定客户",
        "status": p.get("status"),
        "status_label": STATUS_LABELS.get(p.get("status"), p.get("status")),
        "deadline": p.get("deadline") or "",
        "progress": p.get("progress", 0),
        "amount": ("¥{:,.0f}".format(amt) if amt else "—"),
        "risk_tone": p.get("risk_tone", "is-ok"),
        "risk_text": p.get("risk_text", ""),
        "pinned": pinned,
        "can_delete": not is_top1,
        "subtasks": _project_subtasks(conn, p["id"]) if is_top1 else [],
    }
    return d


def _build_key_projects(projects, progress_map, today, max_amount, prefs):
    scored = _score_projects(projects, progress_map, today, max_amount, None)
    pinned = prefs["pinned_top_project_id"]
    manual = prefs["manual_slots"] or []
    hidden = set(prefs["hidden_ids"] or [])

    def find(pid):
        return next((p for p in scored if p["id"] == pid), None)

    top1 = None
    if pinned and pinned not in hidden:
        top1 = find(pinned)
    if top1 is None:
        top1 = next((p for p in scored if p["id"] not in hidden), None)

    exclude = {top1["id"]} if top1 else set()
    pool = [p for p in scored if p["id"] not in exclude and p["id"] not in hidden]

    others = []
    seen = set()
    for m in manual:
        p = find(m)
        if p and p["id"] not in exclude and p["id"] not in hidden and p["id"] not in seen:
            others.append(p)
            seen.add(p["id"])
    for p in pool:
        if len(others) >= 2:
            break
        if p["id"] not in seen:
            others.append(p)
            seen.add(p["id"])

    return top1, others


def _render_dashboard(request: Request, user: dict):
    today = date.today()
    project_ids = get_accessible_project_ids(user)

    with db_session() as conn:
        projects, active_count, due_this_week, pending_payment, leads = _fetch_projects(conn, project_ids)
        progress_map, overdue_set = _compute_progress_overdue(conn, projects, today)

        max_amount = max(
            [float(p.get("budget_max") or p.get("budget_min") or 0) for p in projects],
            default=0,
        ) or 1

        prefs = _get_prefs(conn, user["id"])
        top1, others = _build_key_projects(projects, progress_map, today, max_amount, prefs)
        if top1:
            top1["risk_tone"], top1["risk_text"] = _risk_text(top1)
        for p in others:
            p["risk_tone"], p["risk_text"] = _risk_text(p)

        kp_top1 = _serialize_kp(top1, conn, True, top1 and top1["id"] == prefs["pinned_top_project_id"]) if top1 else None
        kp_others = [_serialize_kp(p, conn, False, False) for p in others]
        kp_count = (1 if kp_top1 else 0) + len(kp_others)

        # 状态分布（4 桶，供 SVG 饼图）
        buckets = {"active": 0, "design": 0, "quoting": 0, "risk": 0}
        for p in projects:
            if p["id"] in overdue_set:
                buckets["risk"] += 1
            elif p["status"] in ("designing", "delivering", "signed", "done"):
                buckets["active"] += 1
            elif p["status"] == "brief":
                buckets["design"] += 1
            elif p["status"] in ("quoting", "lead"):
                buckets["quoting"] += 1
            else:
                buckets["active"] += 1
        total = len(projects) or 1
        ORDER = [
            ("active", "进行中", "#d8ff3f"),
            ("design", "设计中", "#60a5fa"),
            ("quoting", "报价中", "#fbbf24"),
            ("risk", "风险", "#ef4444"),
        ]
        donut_segments, donut_legend, acc = [], [], 0.0
        for key, label, color in ORDER:
            cnt = buckets[key]
            if cnt <= 0:
                donut_legend.append({"label": label, "count": 0, "color": color})
                continue
            frac = cnt / total
            donut_segments.append({
                "label": label, "count": cnt, "color": color,
                "dash": round(frac * 100, 2), "offset": round(acc * 100, 2),
            })
            donut_legend.append({"label": label, "count": cnt, "color": color})
            acc += frac

        # 最近动态
        audit_rows = rows_to_list(
            conn.execute(
                """
                SELECT a.action, a.target_type, a.target_id, a.created_at,
                       c.display_name as actor, p.name as project_name
                FROM audit_log a
                LEFT JOIN collaborators c ON a.actor_id = c.id
                LEFT JOIN projects p ON a.target_type = 'project' AND a.target_id = p.id
                WHERE a.action != 'login'
                ORDER BY a.created_at DESC LIMIT 30
                """
            ).fetchall()
        )
        activity = []
        for a in audit_rows:
            if a["target_type"] == "project" and project_ids is not None and a["target_id"] not in project_ids:
                continue
            verb, icls, icon = ACTIVITY_VERBS.get(a["action"], ("操作了", "i-update", "activity"))
            if a["target_type"] == "project" and a["target_id"]:
                link = f"/app/projects/{a['target_id']}"
                proj = a["project_name"] or "项目"
                text = f"{a['actor'] or '有人'}{verb}<a href='{link}'>{proj}</a>"
            elif a["action"] == "invite":
                link = "/app/settings?tab=members"
                text = f"{a['actor'] or '有人'}{verb}一名新成员"
            else:
                link = "#"
                text = f"{a['actor'] or '有人'}{verb}{a['target_type'] or '内容'}"
            a["verb"] = verb
            a["icls"] = icls
            a["icon"] = icon
            a["link"] = link
            a["text"] = text
            a["time"] = (a["created_at"] or "")[:16]
            activity.append(a)
            if len(activity) >= 5:
                break

        # 近期里程碑（真实数据，替换原写死时间轴）
        timeline = _upcoming_milestones(conn, project_ids, today)

        quick_actions = [
            {"label": "新建项目", "icon": "folder-plus", "url": "/app/projects/new"},
            {"label": "新建线索", "icon": "target", "url": "/app/projects/new?status=lead"},
            {"label": "新建报价", "icon": "file-text", "url": "/app/quotes/new"},
            {"label": "新建任务", "icon": "list-checks", "url": "/app/projects"},
        ]

        promo = {"title": "升级至专业版 · 解锁高级功能与无限项目", "btn": "立即升级 ¥10/月", "visible": True}

        metrics = [
            {"label": "进行中项目", "value": active_count, "icon": "folder-kanban",
             "url": "/app/projects?phase=active", "meta": "进行中", "accent": True},
            {"label": "本周到期", "value": due_this_week, "icon": "clock",
             "url": "/app/projects?due=week", "meta": "本周", "accent": False},
            {"label": "待回款", "value": "¥{:,.0f}".format(pending_payment), "icon": "banknote",
             "url": "/app/quotes?unpaid=1", "meta": "人民币", "accent": False},
            {"label": "待跟进线索", "value": leads, "icon": "target",
             "url": "/app/pipeline?status=lead", "meta": "线索", "accent": False},
        ]

        key_json = json.dumps({"top1": kp_top1, "others": kp_others, "count": kp_count}, ensure_ascii=False)
        all_projects = [{"id": p["id"], "name": p["name"]} for p in projects]

    level = _level_info(user)

    return templates.TemplateResponse(
        "app/dashboard.html",
        {
            "request": request,
            "user": user,
            "level": level,
            "metrics": metrics,
            "key_json": key_json,
            "kp_count": kp_count,
            "all_projects": all_projects,
            "all_projects_json": json.dumps(all_projects, ensure_ascii=False),
            "donut_segments": donut_segments,
            "donut_legend": donut_legend,
            "donut_center": len(projects),
            "timeline": timeline,
            "quick_actions": quick_actions,
            "promo": promo,
            "activity": activity,
        },
    )


@router.get("/", response_class=HTMLResponse)
async def dashboard_redirect():
    """逻辑唯一：/app/ 重定向到 /dashboard（工作台）。"""
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_app(request: Request, user: dict = Depends(get_current_user)):
    return _render_dashboard(request, user)


@router_root.get("/dashboard", response_class=HTMLResponse)
async def dashboard_root(request: Request, user: dict = Depends(get_current_user)):
    return _render_dashboard(request, user)


@router.post("/dashboard/key-projects")
async def key_projects_action(
    request: Request,
    action: str = Form(...),
    project_id: int = Form(None),
    user: dict = Depends(get_current_user),
):
    """重点项目置顶/取消/删除/恢复/排序，持久化到 user_dashboard_prefs。"""
    with db_session() as conn:
        prefs = _get_prefs(conn, user["id"])
        if action == "pin":
            if project_id:
                prefs["pinned_top_project_id"] = project_id
                prefs["hidden_ids"] = [x for x in prefs["hidden_ids"] if x != project_id]
        elif action == "unpin":
            prefs["pinned_top_project_id"] = None
        elif action == "hide":
            if project_id:
                if prefs["pinned_top_project_id"] == project_id:
                    prefs["pinned_top_project_id"] = None
                if project_id not in prefs["hidden_ids"]:
                    prefs["hidden_ids"].append(project_id)
                prefs["manual_slots"] = [x for x in prefs["manual_slots"] if x != project_id]
        elif action == "show":
            if project_id:
                prefs["hidden_ids"] = [x for x in prefs["hidden_ids"] if x != project_id]
                if project_id not in prefs["manual_slots"] and len(prefs["manual_slots"]) < 2:
                    prefs["manual_slots"].append(project_id)
        elif action == "reorder":
            # project_id 视作新顺序里的首个手动槽位
            if project_id and project_id not in prefs["hidden_ids"]:
                prefs["manual_slots"] = [project_id] + [x for x in prefs["manual_slots"] if x != project_id][:1]
        else:
            return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
        _set_prefs(conn, user["id"], **prefs)

        # 重新计算并返回最新结构
        project_ids = get_accessible_project_ids(user)
        projects, _, _, _, _ = _fetch_projects(conn, project_ids)
        progress_map, overdue_set = _compute_progress_overdue(conn, projects, date.today())
        max_amount = max([float(p.get("budget_max") or p.get("budget_min") or 0) for p in projects], default=0) or 1
        top1, others = _build_key_projects(projects, progress_map, date.today(), max_amount, prefs)
        if top1:
            top1["risk_tone"], top1["risk_text"] = _risk_text(top1)
        for p in others:
            p["risk_tone"], p["risk_text"] = _risk_text(p)
        kp_top1 = _serialize_kp(top1, conn, True, top1 and top1["id"] == prefs["pinned_top_project_id"]) if top1 else None
        kp_others = [_serialize_kp(p, conn, False, False) for p in others]
        return JSONResponse({
            "ok": True,
            "top1": kp_top1,
            "others": kp_others,
            "count": (1 if kp_top1 else 0) + len(kp_others),
        })


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline(
    request: Request,
    user: dict = Depends(get_current_user),
    status: str = None,
):
    """线索看板，支持 ?status=<阶段> 筛选（工作台「待跟进线索」联动）。"""
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
    if status:
        columns = [status] if status in columns else columns
    board = {col: [p for p in projects if p["status"] == col] for col in columns}

    return templates.TemplateResponse(
        "app/pipeline.html",
        {
            "request": request,
            "user": user,
            "board": board,
            "status_labels": STATUS_LABELS,
            "active_filter": {"status": status},
        },
    )


@router.post("/pipeline/{project_id}/move")
async def pipeline_move(
    project_id: int,
    status: str = Form(...),
    user: dict = Depends(get_current_user),
):
    if status not in STATUS_LABELS:
        return JSONResponse({"ok": False, "error": "invalid status"}, status_code=400)

    from app.auth import user_can_access_project
    if not user_can_access_project(user, project_id):
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    with db_session() as conn:
        conn.execute(
            "UPDATE projects SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, project_id),
        )
    log_audit(user["id"], "update", "project_status", project_id, f"-> {status}")
    return JSONResponse({"ok": True})
