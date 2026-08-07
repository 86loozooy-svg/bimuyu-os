import json
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import hash_password, log_audit, require_admin, verify_password
from app.config import BASE_DIR, CONTACT_PATH, DATA_DIR
from app.database import db_session, row_to_dict, rows_to_list

UPLOAD_DIR = BASE_DIR / "static" / "uploads"
IMAGE_MAX_BYTES = 5 * 1024 * 1024  # 图片上传上限 5MB
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def save_upload_file(upload: UploadFile, subdir: str = "") -> str:
    """接收图片上传：校验大小/类型，UUID 重命名后保存到 static/uploads/<subdir>/，返回 URL 路径。"""
    content = await upload.read()
    size = len(content)
    if size == 0:
        raise HTTPException(status_code=400, detail="空文件")
    if size > IMAGE_MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件过大，请上传 ≤5MB 的图片")
    mime = _detect_image_type(content)
    if mime is None:
        raise HTTPException(status_code=400, detail="仅支持 JPG / PNG / WebP 格式")
    ext = ALLOWED_IMAGE_TYPES[mime]
    filename = f"{uuid.uuid4().hex}{ext}"
    target_dir = UPLOAD_DIR / subdir if subdir else UPLOAD_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / filename
    dest.write_bytes(content)
    return f"/static/uploads/{subdir}/{filename}" if subdir else f"/static/uploads/{filename}"


def _detect_image_type(content: bytes):
    """按文件头(magic bytes)识别真实图片类型，防止改扩展名绕过校验。"""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"RIFF") and b"WEBP" in content[:16]:
        return "image/webp"
    return None

router = APIRouter(prefix="/app/settings", tags=["settings"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def load_contact() -> dict:
    if CONTACT_PATH.exists():
        return json.loads(CONTACT_PATH.read_text(encoding="utf-8"))
    return {}


@router.get("", response_class=HTMLResponse)
async def settings_index(request: Request, user: dict = Depends(require_admin),     tab: str = "profile"):
    _ensure_account_columns()
    with db_session() as conn:
        studio = row_to_dict(conn.execute("SELECT * FROM studio_profile WHERE id = 1").fetchone())
        collaborators = rows_to_list(
            conn.execute(
                "SELECT * FROM collaborators WHERE revoked = 0 ORDER BY role, email"
            ).fetchall()
        )
        cases = rows_to_list(
            conn.execute("SELECT * FROM cases ORDER BY sort_order, id DESC").fetchall()
        )
        pages = rows_to_list(conn.execute("SELECT * FROM pages").fetchall())
        audit = rows_to_list(
            conn.execute(
                "SELECT a.*, c.display_name, c.email FROM audit_log a "
                "LEFT JOIN collaborators c ON a.actor_id = c.id "
                "ORDER BY a.created_at DESC LIMIT 50"
            ).fetchall()
        )
        projects = rows_to_list(conn.execute("SELECT id, code, name FROM projects").fetchall())
        site_config_rows = rows_to_list(
            conn.execute("SELECT key, value FROM site_config").fetchall()
        )
        client_logos = rows_to_list(
            conn.execute("SELECT * FROM site_client_logos ORDER BY sort_order").fetchall()
        )

    site_config = {r["key"]: r["value"] for r in site_config_rows}

    return templates.TemplateResponse(
        "app/settings/index.html",
        {
            "request": request,
            "user": user,
            "tab": tab,
            "studio": studio,
            "collaborators": collaborators,
            "cases": cases,
            "pages": pages,
            "contact": load_contact(),
            "audit": audit,
            "projects": projects,
            "site": site_config,
            "client_logos": client_logos,
        },
    )


@router.post("/profile")
async def save_profile(
    user: dict = Depends(require_admin),
    name: str = Form(""),
    description: str = Form(""),
    address: str = Form(""),
    tax_id: str = Form(""),
    bank_account: str = Form(""),
    email_signature: str = Form(""),
    revision_policy: str = Form(""),
    default_design_fee_pct: float = Form(15),
    default_management_fee_pct: float = Form(8),
    default_tax_pct: float = Form(6),
    default_margin_pct: float = Form(25),
):
    with db_session() as conn:
        conn.execute(
            """
            UPDATE studio_profile SET name=?, description=?, address=?, tax_id=?,
            bank_account=?, email_signature=?, revision_policy=?,
            default_design_fee_pct=?, default_management_fee_pct=?,
            default_tax_pct=?, default_margin_pct=?
            WHERE id = 1
            """,
            (
                name,
                description,
                address,
                tax_id,
                bank_account,
                email_signature,
                revision_policy,
                default_design_fee_pct,
                default_management_fee_pct,
                default_tax_pct,
                default_margin_pct,
            ),
        )
    log_audit(user["id"], "update", "studio_profile", 1)
    return RedirectResponse(url="/app/settings?tab=profile", status_code=303)


# ----------------------------------------------------------------------------
# 个人账户管理：头像上传、资料更新、修改密码
# collaborators.avatar_url / username 由 _ensure_account_columns 在首次访问时
# 幂等补齐并回填，避免依赖外部迁移脚本（username 与 email 解耦、可独立登录）。
# ----------------------------------------------------------------------------
_account_columns_ready = False


def _ensure_account_columns() -> None:
    """幂等地确保 collaborators 表存在 avatar_url / username 列，并为已有账号回填唯一 username。"""
    global _account_columns_ready
    if _account_columns_ready:
        return
    with db_session() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(collaborators)").fetchall()}
        if "avatar_url" not in cols:
            conn.execute("ALTER TABLE collaborators ADD COLUMN avatar_url TEXT")
        if "username" not in cols:
            conn.execute("ALTER TABLE collaborators ADD COLUMN username TEXT")
        # 为已有账号回填唯一 username（取邮箱@前部分，冲突则追加数字）
        rows = conn.execute(
            "SELECT id, email, username FROM collaborators "
            "WHERE username IS NULL OR username = ''"
        ).fetchall()
        for r in rows:
            base = (r["email"].split("@")[0] if r["email"] else f"user{r['id']}") or f"user{r['id']}"
            uname = base
            i = 1
            while conn.execute(
                "SELECT 1 FROM collaborators WHERE username = ? AND id != ?",
                (uname, r["id"]),
            ).fetchone():
                i += 1
                uname = f"{base}{i}"
            conn.execute(
                "UPDATE collaborators SET username = ? WHERE id = ?", (uname, r["id"])
            )
    _account_columns_ready = True


@router.post("/account/avatar")
async def upload_avatar(
    user: dict = Depends(require_admin),
    avatar: UploadFile = File(...),
):
    _ensure_account_columns()
    image_path = await save_upload_file(avatar, subdir="avatars")
    with db_session() as conn:
        conn.execute(
            "UPDATE collaborators SET avatar_url = ? WHERE id = ?",
            (image_path, user["id"]),
        )
    log_audit(user["id"], "update", "collaborator", user["id"], f"avatar: {image_path}")
    # cropper-upload.js 在 fetch 成功后 window.location.reload()，这里返回 303 即可
    return RedirectResponse(url="/app/settings?tab=account", status_code=303)


@router.post("/account/profile")
async def update_account_profile(
    user: dict = Depends(require_admin),
    display_name: str = Form(""),
    username: str = Form(""),
    email: str = Form(""),
):
    _ensure_account_columns()
    username = (username or "").strip()
    email = (email or "").strip()
    display_name = (display_name or "").strip()
    if not username:
        return RedirectResponse(
            url="/app/settings?tab=account&err=" + _url("登录名不能为空"),
            status_code=303,
        )
    if not email or "@" not in email:
        return RedirectResponse(
            url="/app/settings?tab=account&err=" + _url("邮箱不能为空且需包含 @"),
            status_code=303,
        )
    with db_session() as conn:
        # 登录名唯一性校验（排除自己）
        dup_u = conn.execute(
            "SELECT id FROM collaborators WHERE username = ? AND id != ?",
            (username, user["id"]),
        ).fetchone()
        if dup_u:
            return RedirectResponse(
                url="/app/settings?tab=account&err=" + _url("该登录名已被其他成员占用"),
                status_code=303,
            )
        # 邮箱唯一性校验（排除自己）
        dup_e = conn.execute(
            "SELECT id FROM collaborators WHERE email = ? AND id != ?",
            (email, user["id"]),
        ).fetchone()
        if dup_e:
            return RedirectResponse(
                url="/app/settings?tab=account&err=" + _url("该邮箱已被其他成员占用"),
                status_code=303,
            )
        conn.execute(
            "UPDATE collaborators SET display_name = ?, username = ?, email = ? WHERE id = ?",
            (display_name, username, email, user["id"]),
        )
    log_audit(user["id"], "update", "collaborator", user["id"], "profile")
    return RedirectResponse(url="/app/settings?tab=account&ok=" + _url("资料已保存"), status_code=303)


@router.post("/account/password")
async def change_account_password(
    user: dict = Depends(require_admin),
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
):
    _ensure_account_columns()
    if not verify_password(current_password, user["password_hash"]):
        return RedirectResponse(
            url="/app/settings?tab=account&err=" + _url("原密码错误"),
            status_code=303,
        )
    if len(new_password) < 6:
        return RedirectResponse(
            url="/app/settings?tab=account&err=" + _url("新密码至少 6 位"),
            status_code=303,
        )
    if new_password != confirm_password:
        return RedirectResponse(
            url="/app/settings?tab=account&err=" + _url("两次输入的新密码不一致"),
            status_code=303,
        )
    with db_session() as conn:
        conn.execute(
            "UPDATE collaborators SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user["id"]),
        )
    log_audit(user["id"], "update", "collaborator", user["id"], "password changed")
    return RedirectResponse(url="/app/settings?tab=account&ok=" + _url("密码已修改"), status_code=303)


def _url(text: str) -> str:
    from urllib.parse import quote

    return quote(text)


@router.post("/contact")
async def save_contact(
    user: dict = Depends(require_admin),
    wechat: str = Form(""),
    xiaohongshu_url: str = Form(""),
    douyin_url: str = Form(""),
    phone: str = Form(""),
):
    data = {
        "wechat": wechat,
        "xiaohongshu_url": xiaohongshu_url,
        "douyin_url": douyin_url,
        "phone": phone,
    }
    CONTACT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    log_audit(user["id"], "update", "contact", 0)
    return RedirectResponse(url="/app/settings?tab=public", status_code=303)


@router.post("/cases/new")
async def create_case(
    user: dict = Depends(require_admin),
    slug: str = Form(...),
    title: str = Form(...),
    subtitle: str = Form(""),
    description: str = Form(""),
    sort_order: int = Form(0),
    is_online: str = Form(""),
):
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO cases (slug, title, subtitle, description, sort_order, is_online)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (slug, title, subtitle, description, sort_order, 1 if is_online == "on" else 0),
        )
        case_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    log_audit(user["id"], "create", "case", case_id, title)
    return RedirectResponse(url=f"/app/settings/cases/{case_id}/edit", status_code=303)


@router.post("/cases/{case_id}/toggle")
async def toggle_case(case_id: int, user: dict = Depends(require_admin)):
    with db_session() as conn:
        row = conn.execute("SELECT is_online FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE cases SET is_online = ? WHERE id = ?",
                (0 if row["is_online"] else 1, case_id),
            )
    return RedirectResponse(url="/app/settings?tab=public", status_code=303)


@router.get("/cases/{case_id}/edit", response_class=HTMLResponse)
async def edit_case(request: Request, case_id: int, user: dict = Depends(require_admin)):
    with db_session() as conn:
        case = row_to_dict(
            conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        )
        images = rows_to_list(
            conn.execute(
                "SELECT * FROM case_images WHERE case_id = ? ORDER BY sort_order",
                (case_id,),
            ).fetchall()
        )
    return templates.TemplateResponse(
        "app/settings/case_edit.html",
        {
            "request": request,
            "user": user,
            "case": case,
            "images": images,
        },
    )


@router.post("/cases/{case_id}/edit")
async def update_case(
    case_id: int,
    user: dict = Depends(require_admin),
    title: str = Form(...),
    slug: str = Form(...),
    subtitle: str = Form(""),
    description: str = Form(""),
    sort_order: int = Form(0),
    is_online: str = Form(""),
):
    with db_session() as conn:
        conn.execute(
            """
            UPDATE cases SET title=?, slug=?, subtitle=?, description=?,
            sort_order=?, is_online=? WHERE id=?
            """,
            (title, slug, subtitle, description, sort_order, 1 if is_online == "on" else 0, case_id),
        )
    log_audit(user["id"], "update", "case", case_id, title)
    return RedirectResponse(url=f"/app/settings/cases/{case_id}/edit", status_code=303)


@router.post("/cases/{case_id}/cover")
async def upload_cover(
    case_id: int,
    user: dict = Depends(require_admin),
    cover: UploadFile = File(...),
):
    image_path = await save_upload_file(cover)
    with db_session() as conn:
        conn.execute("UPDATE cases SET cover_image=? WHERE id=?", (image_path, case_id))
    log_audit(user["id"], "update", "case", case_id, f"cover: {image_path}")
    return RedirectResponse(url=f"/app/settings/cases/{case_id}/edit", status_code=303)


@router.post("/cases/{case_id}/images")
async def add_case_image(
    case_id: int,
    user: dict = Depends(require_admin),
    image: UploadFile = File(...),
    caption: str = Form(""),
):
    image_path = await save_upload_file(image)
    with db_session() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM case_images WHERE case_id=?",
            (case_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO case_images (case_id, image_path, caption, sort_order) VALUES (?, ?, ?, ?)",
            (case_id, image_path, caption, max_order + 1),
        )
    log_audit(user["id"], "create", "case_image", case_id, caption)
    return RedirectResponse(url=f"/app/settings/cases/{case_id}/edit", status_code=303)


@router.post("/cases/{case_id}/images/{image_id}/caption")
async def update_image_caption(
    case_id: int,
    image_id: int,
    user: dict = Depends(require_admin),
    caption: str = Form(""),
):
    with db_session() as conn:
        conn.execute("UPDATE case_images SET caption=? WHERE id=?", (caption, image_id))
    return RedirectResponse(url=f"/app/settings/cases/{case_id}/edit", status_code=303)


@router.post("/cases/{case_id}/images/{image_id}/delete")
async def delete_case_image(
    case_id: int,
    image_id: int,
    user: dict = Depends(require_admin),
):
    with db_session() as conn:
        conn.execute("DELETE FROM case_images WHERE id=?", (image_id,))
    log_audit(user["id"], "delete", "case_image", image_id)
    return RedirectResponse(url=f"/app/settings/cases/{case_id}/edit", status_code=303)


@router.post("/cases/{case_id}/delete")
async def delete_case(case_id: int, user: dict = Depends(require_admin)):
    with db_session() as conn:
        conn.execute("DELETE FROM case_images WHERE case_id=?", (case_id,))
        conn.execute("DELETE FROM cases WHERE id=?", (case_id,))
    log_audit(user["id"], "delete", "case", case_id)
    return RedirectResponse(url="/app/settings?tab=public", status_code=303)


@router.post("/collaborators/invite")
async def invite_collaborator(
    user: dict = Depends(require_admin),
    email: str = Form(...),
    display_name: str = Form(""),
    role: str = Form("viewer"),
    project_ids: str = Form("[]"),
    expires_days: int = Form(30),
):
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
    temp_password = secrets.token_urlsafe(12)

    with db_session() as conn:
        existing = conn.execute(
            "SELECT id FROM collaborators WHERE email = ?", (email.strip(),)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE collaborators SET display_name=?, role=?, project_ids=?,
                token=?, expires_at=?, revoked=0, invited_by=?, invited_at=CURRENT_TIMESTAMP
                WHERE email=?
                """,
                (
                    display_name,
                    role,
                    project_ids,
                    token,
                    expires_at,
                    user["email"],
                    email.strip(),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO collaborators (email, username, password_hash, display_name, role,
                project_ids, invited_by, invited_at, expires_at, token)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (
                    email.strip(),
                    email.strip().split("@")[0],
                    hash_password(temp_password),
                    display_name,
                    role,
                    project_ids,
                    user["email"],
                    expires_at,
                    token,
                ),
            )
            collab_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            log_audit(user["id"], "invite", "collaborator", collab_id, email)

    return RedirectResponse(
        url=f"/app/settings?tab=members&invite_token={token}&temp_pass={temp_password}",
        status_code=303,
    )


@router.post("/collaborators/{collab_id}/revoke")
async def revoke_collaborator(collab_id: int, user: dict = Depends(require_admin)):
    with db_session() as conn:
        conn.execute(
            "UPDATE collaborators SET revoked = 1, token = NULL WHERE id = ? AND role != 'admin'",
            (collab_id,),
        )
    log_audit(user["id"], "revoke", "collaborator", collab_id)
    return RedirectResponse(url="/app/settings?tab=members", status_code=303)


@router.post("/about")
async def save_about(user: dict = Depends(require_admin), body_md: str = Form("")):
    with db_session() as conn:
        conn.execute(
            "UPDATE pages SET body_md = ? WHERE slug = 'about'",
            (body_md,),
        )
    log_audit(user["id"], "update", "page", 1, "about")
    return RedirectResponse(url="/app/settings?tab=public", status_code=303)


@router.post("/homepage")
async def save_homepage(
    user: dict = Depends(require_admin),
    hero_title: str = Form(""),
    hero_subtitle: str = Form(""),
    hero_btn_text: str = Form(""),
    hero_btn_link: str = Form(""),
    hero_bg: str = Form(""),
    biz_title: str = Form(""),
    biz_subtitle: str = Form(""),
    biz_text: str = Form(""),
    biz_btn_text: str = Form(""),
    biz_btn_link: str = Form(""),
    clients_title: str = Form(""),
    clients_subtitle: str = Form(""),
):
    updates = {
        "hero_title": hero_title,
        "hero_subtitle": hero_subtitle,
        "hero_btn_text": hero_btn_text,
        "hero_btn_link": hero_btn_link,
        "hero_bg": hero_bg,
        "biz_title": biz_title,
        "biz_subtitle": biz_subtitle,
        "biz_text": biz_text,
        "biz_btn_text": biz_btn_text,
        "biz_btn_link": biz_btn_link,
        "clients_title": clients_title,
        "clients_subtitle": clients_subtitle,
    }
    with db_session() as conn:
        for key, value in updates.items():
            conn.execute(
                "UPDATE site_config SET value=?, updated_at=CURRENT_TIMESTAMP WHERE key=?",
                (value, key),
            )
    log_audit(user["id"], "update", "site_config", 0, "homepage")
    return RedirectResponse(url="/app/settings?tab=homepage", status_code=303)


@router.post("/biz-image")
async def upload_biz_image(
    user: dict = Depends(require_admin),
    image: UploadFile = File(...),
):
    image_path = await save_upload_file(image)
    with db_session() as conn:
        conn.execute("UPDATE site_config SET value=? WHERE key='biz_image'", (image_path,))
    log_audit(user["id"], "update", "site_config", 0, f"biz_image: {image_path}")
    return RedirectResponse(url="/app/settings?tab=homepage", status_code=303)


@router.post("/client-logos/new")
async def add_client_logo(
    user: dict = Depends(require_admin),
    name: str = Form(...),
):
    with db_session() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM site_client_logos"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO site_client_logos (name, sort_order) VALUES (?, ?)",
            (name, max_order + 1),
        )
    return RedirectResponse(url="/app/settings?tab=homepage", status_code=303)


@router.post("/client-logos/{logo_id}/upload")
async def upload_client_logo(
    logo_id: int,
    user: dict = Depends(require_admin),
    logo: UploadFile = File(...),
):
    image_path = await save_upload_file(logo)
    with db_session() as conn:
        conn.execute("UPDATE site_client_logos SET logo_path=? WHERE id=?", (image_path, logo_id))
    return RedirectResponse(url="/app/settings?tab=homepage", status_code=303)


@router.post("/client-logos/{logo_id}/toggle")
async def toggle_client_logo(logo_id: int, user: dict = Depends(require_admin)):
    with db_session() as conn:
        row = conn.execute("SELECT is_visible FROM site_client_logos WHERE id=?", (logo_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE site_client_logos SET is_visible=? WHERE id=?",
                (0 if row["is_visible"] else 1, logo_id),
            )
    return RedirectResponse(url="/app/settings?tab=homepage", status_code=303)


@router.post("/client-logos/{logo_id}/delete")
async def delete_client_logo(logo_id: int, user: dict = Depends(require_admin)):
    with db_session() as conn:
        conn.execute("DELETE FROM site_client_logos WHERE id=?", (logo_id,))
    return RedirectResponse(url="/app/settings?tab=homepage", status_code=303)
