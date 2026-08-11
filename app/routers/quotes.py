from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_accessible_project_ids, get_current_user
from app.config import BASE_DIR
from app.database import db_session, rows_to_list

router = APIRouter(prefix="/app/quotes", tags=["quotes"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("", response_class=HTMLResponse)
async def quotes_list(
    request: Request,
    user: dict = Depends(get_current_user),
    unpaid: str = None,
    status: str = None,
):
    """报价单列表，支持 ?unpaid=1（待回款）与 ?status=<阶段> 筛选（驾驶舱指标卡联动）。"""
    project_ids = get_accessible_project_ids(user)
    extra = ""
    if unpaid:
        extra = " AND q.project_id IN (SELECT project_id FROM invoices WHERE paid = 0)"
    if status:
        extra += f" AND q.status = '{status}'"
    with db_session() as conn:
        if project_ids is None:
            quotes = rows_to_list(
                conn.execute(
                    f"""
                    SELECT q.*, p.name as project_name, p.code as project_code,
                           t.name as template_name
                    FROM quotes q
                    JOIN projects p ON q.project_id = p.id
                    LEFT JOIN boq_templates t ON q.template_id = t.id
                    WHERE 1=1 {extra}
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
                    WHERE q.project_id IN ({placeholders}) {extra}
                    ORDER BY q.created_at DESC
                    """,
                    project_ids,
                ).fetchall()
            )
        else:
            quotes = []

    # 统计口径（对齐参考 #quotations：待确认 / 已确认 / 已作废 + 总额）
    _PENDING = {"draft", "pending", "submitted"}
    _CONFIRMED = {"confirmed", "approved"}
    _VOID = {"void", "cancelled"}
    quote_stats = {"pending": 0, "confirmed": 0, "void": 0, "total": len(quotes), "amount": 0}
    for q in quotes:
        s = (q.get("status") or "").lower()
        if s in _PENDING:
            quote_stats["pending"] += 1
        elif s in _CONFIRMED:
            quote_stats["confirmed"] += 1
        elif s in _VOID:
            quote_stats["void"] += 1
        if q.get("total") is not None:
            try:
                quote_stats["amount"] += float(q["total"])
            except (TypeError, ValueError):
                pass

    if user["role"] == "viewer":
        for q in quotes:
            q["total"] = None

    return templates.TemplateResponse(
        "app/quotes/index.html",
        {
            "request": request,
            "user": user,
            "quotes": quotes,
            "quote_stats": quote_stats,
            "active_filter": {"unpaid": unpaid, "status": status},
        },
    )
