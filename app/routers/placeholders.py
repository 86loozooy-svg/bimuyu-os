"""占位路由：为导航规范里尚未实现的页面提供最小可用骨架，避免 404。"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_admin
from app.config import BASE_DIR

router = APIRouter(prefix="/app", tags=["placeholders"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/modules", response_class=HTMLResponse)
async def modules_page(request: Request, user: dict = Depends(require_admin)):
    return templates.TemplateResponse(
        "app/placeholder.html",
        {
            "request": request,
            "user": user,
            "title": "模块管理",
            "desc": "启用 / 停用工作台功能模块（如报价引擎、灵感采集、Pipeline 看板等）。该模块正在规划中。",
        },
    )
