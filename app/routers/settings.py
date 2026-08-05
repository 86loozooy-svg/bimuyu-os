import json
import secrets
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import hash_password, log_audit, require_admin
from app.config import BASE_DIR, CONTACT_PATH, DATA_DIR
from app.database import db_session, row_to_dict, rows_to_list

UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}


def save_upload_file(upload: UploadFile) -> str:
    """Save an uploaded image to static/uploads/ and return the URL path."""
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return f"/static/uploads/{filename}"

router = APIRouter(prefix="/app/settings", tags=["settings"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def load_contact() -> dict:
    if CONTACT_PATH.exists():
        return json.loads(CONTACT_PATH.read_text(encoding="utf-8"))
    return {}


@router.get("", response_class=HTMLResponse)
async def settings_index(request: Request, user: dict = Depends(require_admin), tab: str = "profile"):
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
    image_path = save_upload_file(cover)
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
    image_path = save_upload_file(image)
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
                INSERT INTO collaborators (email, password_hash, display_name, role,
                project_ids, invited_by, invited_at, expires_at, token)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (
                    email.strip(),
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
    image_path = save_upload_file(image)
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
    image_path = save_upload_file(logo)
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
