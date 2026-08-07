"""待办模块：手动创建、完成切换、删除、手动触发推送、站内红点计数，
以及里程碑自动生成任务（供 projects.py 调用）。"""

from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, log_audit, require_admin
from app.config import BASE_DIR
from app.database import db_session, rows_to_list

router = APIRouter(prefix="/app/tasks", tags=["tasks"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
SOURCE_LABELS = {"manual": "手动", "milestone": "里程碑"}


# ---------------------------------------------------------------------------
# 里程碑 → 任务 自动同步（由 projects.py 的里程碑增删改调用）
# ---------------------------------------------------------------------------
def sync_task_from_milestone(conn, project_id: int, milestone: dict) -> int | None:
    """根据里程碑创建/更新关联任务。返回任务 id。"""
    mid = milestone.get("id")
    name = (milestone.get("name") or "").strip()
    if not name:
        return None
    due = milestone.get("end_date") or milestone.get("due_date")
    if not due:
        return None
    existing = conn.execute(
        "SELECT id FROM task WHERE milestone_id = ?", (mid,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE task SET title = ?, due_date = ?, project_id = ? "
            "WHERE id = ?",
            (f"里程碑：{name}", due, project_id, existing["id"]),
        )
        return existing["id"]
    conn.execute(
        """
        INSERT INTO task (project_id, title, due_date, priority, status,
                          source, milestone_id)
        VALUES (?, ?, ?, 'high', 'todo', 'milestone', ?)
        """,
        (project_id, f"里程碑：{name}", due, mid),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def delete_tasks_for_milestone(conn, milestone_id: int) -> None:
    conn.execute("DELETE FROM task WHERE milestone_id = ?", (milestone_id,))


# ---------------------------------------------------------------------------
# 页面与 CRUD
# ---------------------------------------------------------------------------
@router.get("", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    status: str = Query("all"),
    user: dict = Depends(get_current_user),
):
    with db_session() as conn:
        # 项目下拉（用于新建待办时关联）
        projects = rows_to_list(
            conn.execute(
                "SELECT p.id, p.code, p.name, c.name as client_name FROM projects p "
                "LEFT JOIN clients c ON p.client_id = c.id ORDER BY p.updated_at DESC"
            ).fetchall()
        )
        if status == "open":
            rows = conn.execute(
                "SELECT * FROM task WHERE status != 'done' ORDER BY due_date, priority DESC"
            ).fetchall()
        elif status == "done":
            rows = conn.execute(
                "SELECT * FROM task WHERE status = 'done' ORDER BY done_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM task ORDER BY "
                "(status='done'), due_date, priority DESC"
            ).fetchall()
        tasks = rows_to_list(rows)
        # 补充项目名称
        proj_name = {p["id"]: p["name"] for p in projects}
        for t in tasks:
            t["project_name"] = proj_name.get(t.get("project_id")) if t.get("project_id") else None
        today = date.today().isoformat()
        pending_today = conn.execute(
            "SELECT COUNT(*) FROM task WHERE status != 'done' AND due_date <= ?",
            (today,),
        ).fetchone()[0]

    return templates.TemplateResponse(
        "app/tasks.html",
        {
            "request": request,
            "user": user,
            "tasks": tasks,
            "projects": projects,
            "status_filter": status,
            "pending_today": pending_today,
            "priority_labels": PRIORITY_LABELS,
            "source_labels": SOURCE_LABELS,
        },
    )


@router.post("/new")
async def create_task(
    user: dict = Depends(get_current_user),
    title: str = Form(...),
    project_id: int = Form(0),
    due_date: str = Form(""),
    due_time: str = Form(""),
    priority: str = Form("medium"),
    assignee: str = Form(""),
    description: str = Form(""),
):
    title = (title or "").strip()
    if not title:
        return RedirectResponse(url="/app/tasks", status_code=303)
    pid = project_id or None
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO task (project_id, title, description, due_date, due_time,
                              priority, assignee, source, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', ?)
            """,
            (
                pid,
                title,
                description or None,
                due_date or None,
                due_time or None,
                priority,
                assignee or None,
                user["id"],
            ),
        )
    log_audit(user["id"], "create", "task", 0, title)
    return RedirectResponse(url="/app/tasks", status_code=303)


@router.post("/{task_id}/toggle")
async def toggle_task(task_id: int, user: dict = Depends(get_current_user)):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return RedirectResponse(url="/app/tasks", status_code=303)
        new_status = "done" if row["status"] != "done" else "todo"
        done_at = "CURRENT_TIMESTAMP" if new_status == "done" else None
        if done_at:
            conn.execute(
                "UPDATE task SET status = ?, done_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_status, task_id),
            )
        else:
            conn.execute(
                "UPDATE task SET status = ?, done_at = NULL WHERE id = ?",
                (new_status, task_id),
            )
    return RedirectResponse(url="/app/tasks", status_code=303)


@router.post("/{task_id}/delete")
async def delete_task(task_id: int, user: dict = Depends(get_current_user)):
    with db_session() as conn:
        conn.execute("DELETE FROM task WHERE id = ?", (task_id,))
    log_audit(user["id"], "delete", "task", task_id)
    return RedirectResponse(url="/app/tasks", status_code=303)


@router.post("/push-now")
async def push_now(user: dict = Depends(require_admin)):
    """管理员手动触发一次每日推送（用于测试/即时提醒）。"""
    from app.services import push

    summary = push.scan_and_push()
    pushed = summary.get("pushed", 0)
    return RedirectResponse(url=f"/app/tasks?pushed={pushed}", status_code=303)


@router.get("/count")
async def tasks_count(user: dict = Depends(get_current_user)):
    """站内红点：返回到期未完成任务数。"""
    today = date.today().isoformat()
    with db_session() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) FROM task WHERE status != 'done' AND due_date <= ?",
            (today,),
        ).fetchone()[0]
    return JSONResponse({"pending_today": pending})
