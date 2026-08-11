"""分享查看：只读令牌安全模型。

安全要点：
- 令牌随机（secrets.token_urlsafe），不可猜测；
- 只读：查看页不提供任何写/改操作，且不暴露成本/利润等敏感字段；
- 可吊销：created_by 可随时 revoke；
- 频控：按 token+IP 限流，防止令牌被刷；
- 有效期：expires_at 到点即失效。
"""
from collections import defaultdict
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, hash_password, verify_password
from app.config import BASE_DIR
from app.database import db_session, row_to_dict, rows_to_list

router = APIRouter(prefix="/app/share", tags=["share"])
# 公开只读查看页走根路径 /share/{token}（不强制登录，且不被 /app 鉴权中间件拦截）
public_router = APIRouter(tags=["share-public"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# 频控：{f"{token}:{ip}": [ts, ...]}，窗口 60s 内最多 40 次
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 40
_access_log: dict[str, list[float]] = defaultdict(list)


def _rate_ok(token: str, ip: str) -> bool:
    key = f"{token}:{ip}"
    now = datetime.now().timestamp()
    buf = _access_log[key]
    # 清理窗口外记录
    _access_log[key] = [t for t in buf if now - t < _RATE_LIMIT_WINDOW]
    if len(_access_log[key]) >= _RATE_LIMIT_MAX:
        return False
    _access_log[key].append(now)
    return True


VALID_TARGETS = {"project", "case"}
VALID_ACCESS_MODES = {"link", "password"}


def _build_short_url(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/share/{token}"


@router.post("/create")
async def create_share(
    request: Request,
    user: dict = Depends(get_current_user),
    target_type: str = Form(...),
    target_id: int = Form(0),
    title: str = Form(""),
    access_mode: str = Form("link"),
    password: str = Form(""),
    expires_in: str = Form("7d"),
):
    if target_type not in VALID_TARGETS:
        raise HTTPException(status_code=400, detail="不支持的分享类型")
    if access_mode not in VALID_ACCESS_MODES:
        raise HTTPException(status_code=400, detail="不支持的访问方式")
    if access_mode == "password" and len(password) < 4:
        raise HTTPException(status_code=400, detail="密码至少 4 位")

    # 校验目标存在性（仅 project 当前落地）
    with db_session() as conn:
        if target_type == "project":
            row = conn.execute(
                "SELECT id, name, code FROM projects WHERE id = ?", (target_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="项目不存在")
            resolved_title = title or (row["name"] or f"项目 {row['code']}")
        elif target_type == "case":
            row = conn.execute(
                "SELECT id, title FROM cases WHERE id = ?", (target_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="案例不存在")
            resolved_title = title or (row["title"] or f"案例 {row['id']}")
        else:
            resolved_title = title or "分享"

    token = secrets.token_urlsafe(16)
    exp = None
    if expires_in and expires_in != "never":
        try:
            num = int(expires_in[:-1])
            unit = expires_in[-1]
            if unit == "h":
                exp = (datetime.now(timezone.utc) + timedelta(hours=num)).isoformat()
            elif unit == "d":
                exp = (datetime.now(timezone.utc) + timedelta(days=num)).isoformat()
            elif unit == "m":
                exp = (datetime.now(timezone.utc) + timedelta(minutes=num)).isoformat()
        except Exception:
            exp = None

    pw_hash = hash_password(password) if access_mode == "password" else None
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO share_tokens
            (token, created_by, target_type, target_id, permission, access_mode,
             password_hash, expires_at, title)
            VALUES (?, ?, ?, ?, 'readonly', ?, ?, ?, ?)
            """,
            (token, user["id"], target_type, target_id, access_mode, pw_hash, exp, resolved_title),
        )

    return JSONResponse(
        {
            "ok": True,
            "token": token,
            "short_url": _build_short_url(request, token),
            "expires_at": exp,
            "access_mode": access_mode,
        }
    )


@router.get("/list", response_class=JSONResponse)
async def list_shares(user: dict = Depends(get_current_user)):
    with db_session() as conn:
        rows = rows_to_list(
            conn.execute(
                "SELECT * FROM share_tokens WHERE created_by = ? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall()
        )
    now = datetime.now(timezone.utc)
    out = []
    for r in rows:
        expired = bool(r["expires_at"]) and datetime.fromisoformat(r["expires_at"]) < now
        out.append(
            {
                "token": r["token"],
                "title": r["title"],
                "target_type": r["target_type"],
                "target_id": r["target_id"],
                "access_mode": r["access_mode"],
                "expires_at": r["expires_at"],
                "revoked": bool(r["revoked"]),
                "expired": expired,
                "access_count": r["access_count"],
                "created_at": r["created_at"],
            }
        )
    return JSONResponse({"ok": True, "items": out})


@router.post("/{token}/revoke")
async def revoke_share(token: str, user: dict = Depends(get_current_user)):
    with db_session() as conn:
        row = row_to_dict(
            conn.execute("SELECT * FROM share_tokens WHERE token = ?", (token,)).fetchone()
        )
        if not row:
            raise HTTPException(status_code=404, detail="分享不存在")
        if row["created_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="无权操作此分享")
        conn.execute("UPDATE share_tokens SET revoked = 1 WHERE token = ?", (token,))
    return JSONResponse({"ok": True})


@public_router.get("/share/{token}", response_class=HTMLResponse)
async def view_share(
    request: Request,
    token: str,
    user: Optional[dict] = None,  # 不强制登录：分享查看是公开的只读入口
    password: str = Form(""),
):
    client_ip = request.client.host if request.client else "0.0.0.0"
    if not _rate_ok(token, client_ip):
        return HTMLResponse(
            "<h1>访问过于频繁</h1><p>请稍后再试。</p>", status_code=429
        )

    with db_session() as conn:
        row = row_to_dict(
            conn.execute("SELECT * FROM share_tokens WHERE token = ?", (token,)).fetchone()
        )
        if not row:
            return templates.TemplateResponse(
                "app/shared/error.html",
                {"request": request, "code": 404, "msg": "分享链接不存在或已被删除"},
                status_code=404,
            )
        if row["revoked"]:
            return templates.TemplateResponse(
                "app/shared/error.html",
                {"request": request, "code": 410, "msg": "该分享已被创建者吊销"},
                status_code=410,
            )
        now = datetime.now(timezone.utc)
        if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) < now:
            return templates.TemplateResponse(
                "app/shared/error.html",
                {"request": request, "code": 410, "msg": "该分享已过期"},
                status_code=410,
            )

        # 密码访问模式：校验 cookie 或本次提交的密码
        need_pw = row["access_mode"] == "password" and row["password_hash"]
        authed = False
        if need_pw:
            cookie = request.cookies.get(f"sharepw_{token}")
            if cookie == "1":
                authed = True
            elif password:
                if verify_password(password, row["password_hash"]):
                    authed = True
                else:
                    return templates.TemplateResponse(
                        "app/shared/password.html",
                        {"request": request, "token": token, "error": "密码错误"},
                        status_code=401,
                    )
            if not authed:
                return templates.TemplateResponse(
                    "app/shared/password.html",
                    {"request": request, "token": token, "error": ""},
                )

        # 取出只读内容（不暴露成本/利润等敏感字段）
        payload = None
        if row["target_type"] == "project":
            p = row_to_dict(
                conn.execute(
                    "SELECT p.id, p.code, p.name, p.status, p.brief_md AS description, c.name AS client_name, p.deadline "
                    "FROM projects p LEFT JOIN clients c ON p.client_id = c.id "
                    "WHERE p.id = ?",
                    (row["target_id"],),
                ).fetchone()
            )
            if p:
                milestones = rows_to_list(
                    conn.execute(
                        "SELECT name AS title, due_date, done, status FROM project_milestones "
                        "WHERE project_id = ? ORDER BY due_date",
                        (row["target_id"],),
                    ).fetchall()
                )
                payload = {"type": "project", "project": p, "milestones": milestones}
        elif row["target_type"] == "case":
            c = row_to_dict(
                conn.execute(
                    "SELECT id, title, subtitle, description FROM cases WHERE id = ?",
                    (row["target_id"],),
                ).fetchone()
            )
            payload = {"type": "case", "case": c} if c else None

        if not authed and need_pw:
            # 密码已校验通过但还未种 cookie（shouldn't happen since handled above）
            pass

        # 计数 + 更新最近访问
        conn.execute(
            "UPDATE share_tokens SET access_count = access_count + 1, "
            "last_access_at = ? WHERE token = ?",
            (now.isoformat(), token),
        )

    # 密码模式：校验成功后种 cookie（仅当本次通过）
    resp = templates.TemplateResponse(
        "app/shared/view.html",
        {"request": request, "share": row, "payload": payload},
    )
    if need_pw and authed and not request.cookies.get(f"sharepw_{token}"):
        resp.set_cookie(key=f"sharepw_{token}", value="1", samesite="lax", max_age=3600 * 24)
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@public_router.post("/share/{token}", response_class=HTMLResponse)
async def view_share_password(request: Request, token: str, password: str = Form("")):
    """密码模式：提交密码后内部转发到 GET 处理。"""
    return await view_share(request, token, password=password)
