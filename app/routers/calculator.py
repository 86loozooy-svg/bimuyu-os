"""工程计算器路由."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user
from app.config import BASE_DIR

router = APIRouter(prefix="/app/calculator", tags=["calculator"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("", response_class=HTMLResponse)
async def calculator_page(
    request: Request,
    user: dict = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "app/calculator/index.html",
        {"request": request, "user": user},
    )
