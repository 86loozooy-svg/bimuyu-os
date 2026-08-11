"""P3 消息中心：站内通知 UI 层。

- 列表页 /app/notifications（支持 ?type= 过滤）+ 标记已读 / 全部已读
- 顶栏铃铛所需 JSON：/unread-count（未读数）、/recent（最近 6 条）
- 通道偏好：POST /prefs（admin，写入 notification_prefs）
- 单租户：通知全局可见，任意已登录用户可查看 / 标记已读
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, require_admin
from app.config import BASE_DIR
from app.services import notifications as notif

router = APIRouter(prefix="/app/notifications", tags=["notifications"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _referer(request: Request, fallback: str = "/app/notifications") -> str:
    return request.headers.get("referer") or fallback


@router.get("", response_class=HTMLResponse)
async def notification_list(
    request: Request,
    user: dict = Depends(get_current_user),
    type: str = "",
):
    items = notif.list_notifications(limit=50, type_filter=type or None)
    return templates.TemplateResponse(
        "app/notifications.html",
        {
            "request": request,
            "user": user,
            "items": items,
            "type_filter": type,
            "unread": notif.unread_count(),
            "type_labels": notif.TYPE_LABELS,
        },
    )


@router.get("/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    return JSONResponse({"count": notif.unread_count()})


@router.get("/recent")
async def recent_notifications(user: dict = Depends(get_current_user)):
    rows = notif.recent(limit=6)
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "type": r["type"],
                "title": r["title"],
                "body": r["body"] or "",
                "link": r["link"] or "",
                "is_read": bool(r["is_read"]),
                "created_at": r["created_at"],
            }
        )
    return JSONResponse({"items": out, "count": notif.unread_count()})


@router.post("/{nid}/read")
async def read_one(nid: int, request: Request, user: dict = Depends(get_current_user)):
    notif.mark_read(nid)
    return RedirectResponse(url=_referer(request), status_code=303)


@router.post("/read-all")
async def read_all(request: Request, user: dict = Depends(get_current_user)):
    notif.mark_all_read()
    return RedirectResponse(url=_referer(request), status_code=303)


@router.post("/prefs")
async def save_prefs(
    request: Request,
    user: dict = Depends(require_admin),
    in_app: str = Form(""),
    email: str = Form(""),
    wecom: str = Form(""),
):
    notif.set_pref("in_app", in_app == "on")
    notif.set_pref("email", email == "on")
    notif.set_pref("wecom", wecom == "on")
    return RedirectResponse(url="/app/settings?tab=notification&ok=prefs", status_code=303)
