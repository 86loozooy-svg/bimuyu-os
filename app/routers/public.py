import json
from pathlib import Path

import markdown
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, CONTACT_PATH
from app.database import db_session, row_to_dict, rows_to_list

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def load_contact() -> dict:
    if CONTACT_PATH.exists():
        return json.loads(CONTACT_PATH.read_text(encoding="utf-8"))
    return {}


def get_studio_profile() -> dict:
    with db_session() as conn:
        return row_to_dict(conn.execute("SELECT * FROM studio_profile WHERE id = 1").fetchone()) or {}


def load_site_config() -> dict:
    """Load all key-value pairs from site_config table."""
    with db_session() as conn:
        rows = rows_to_list(
            conn.execute("SELECT key, value FROM site_config").fetchall()
        )
    return {r["key"]: r["value"] for r in rows}


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    with db_session() as conn:
        cases = rows_to_list(
            conn.execute(
                """
                SELECT * FROM cases WHERE is_online = 1
                ORDER BY sort_order, id DESC LIMIT 6
                """
            ).fetchall()
        )
        client_logos = rows_to_list(
            conn.execute(
                "SELECT * FROM site_client_logos WHERE is_visible = 1 ORDER BY sort_order"
            ).fetchall()
        )
    return templates.TemplateResponse(
        "public/index.html",
        {
            "request": request,
            "studio": get_studio_profile(),
            "cases": cases,
            "contact": load_contact(),
            "site": load_site_config(),
            "client_logos": client_logos,
        },
    )


@router.get("/cases", response_class=HTMLResponse)
async def cases_list(request: Request):
    with db_session() as conn:
        cases = rows_to_list(
            conn.execute(
                "SELECT * FROM cases WHERE is_online = 1 ORDER BY sort_order, id DESC"
            ).fetchall()
        )
    return templates.TemplateResponse(
        "public/cases.html",
        {
            "request": request,
            "studio": get_studio_profile(),
            "cases": cases,
            "contact": load_contact(),
        },
    )


@router.get("/cases/{slug}", response_class=HTMLResponse)
async def case_detail(request: Request, slug: str):
    with db_session() as conn:
        case = row_to_dict(
            conn.execute(
                "SELECT * FROM cases WHERE slug = ? AND is_online = 1", (slug,)
            ).fetchone()
        )
        if not case:
            raise HTTPException(status_code=404, detail="案例不存在")
        images = rows_to_list(
            conn.execute(
                "SELECT * FROM case_images WHERE case_id = ? ORDER BY sort_order",
                (case["id"],),
            ).fetchall()
        )
    return templates.TemplateResponse(
        "public/case_detail.html",
        {
            "request": request,
            "studio": get_studio_profile(),
            "case": case,
            "images": images,
            "contact": load_contact(),
        },
    )


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    with db_session() as conn:
        page = row_to_dict(
            conn.execute("SELECT * FROM pages WHERE slug = 'about'").fetchone()
        )
    body_html = ""
    if page and page.get("body_md"):
        body_html = markdown.markdown(page["body_md"], extensions=["extra"])
    return templates.TemplateResponse(
        "public/about.html",
        {
            "request": request,
            "studio": get_studio_profile(),
            "page": page,
            "body_html": body_html,
            "contact": load_contact(),
        },
    )
