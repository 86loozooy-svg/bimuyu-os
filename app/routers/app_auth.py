from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import authenticate_user, create_access_token, get_current_user, log_audit
from app.config import ACCESS_TOKEN_EXPIRE_HOURS, BASE_DIR, COOKIE_NAME, DEFAULT_ADMIN_EMAIL
from app.database import db_session

router = APIRouter(prefix="/app", tags=["auth"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "app/login.html",
        {"request": request, "error": None},
    )


@router.post("/login")
async def login_submit(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
):
    user = authenticate_user(email.strip(), password)
    if not user:
        return templates.TemplateResponse(
            "app/login.html",
            {"request": {}, "error": "邮箱或密码错误"},
            status_code=400,
        )
    token = create_access_token({"sub": str(user["id"]), "role": user["role"]})
    with db_session() as conn:
        conn.execute(
            "UPDATE collaborators SET last_access_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), user["id"]),
        )
    log_audit(user["id"], "login", "user", user["id"])
    redirect = RedirectResponse(url="/app/", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        samesite="lax",
    )
    return redirect


@router.get("/logout")
async def logout():
    redirect = RedirectResponse(url="/app/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(COOKIE_NAME)
    return redirect


@router.get("/accept-invite", response_class=HTMLResponse)
async def accept_invite_page(request: Request, token: str = ""):
    return templates.TemplateResponse(
        "app/accept_invite.html",
        {"request": request, "token": token, "error": None},
    )
