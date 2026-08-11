"""个人账户页：任意登录用户可访问（不限于 admin）。

个人资料 / 密码 / 头像的写接口已放宽到本人（见 settings.py），
此处仅负责渲染账户页，并把原本平铺在侧栏 footer 的「退出登录」等
快捷操作收敛到本页。
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.config import BASE_DIR
from app.database import db_session
from app.routers import settings as settings_module

router = APIRouter(prefix="/app", tags=["account"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, user: dict = Depends(get_current_user)):
    settings_module._ensure_account_columns()
    with db_session() as conn:
        # 仅取本人所需字段，避免暴露他人信息
        fresh = conn.execute(
            "SELECT id, display_name, username, email, avatar_url, role, membership_level "
            "FROM collaborators WHERE id = ?",
            (user["id"],),
        ).fetchone()
    me = dict(fresh) if fresh else user
    return templates.TemplateResponse(
        "app/account.html",
        {"request": request, "user": me},
    )
