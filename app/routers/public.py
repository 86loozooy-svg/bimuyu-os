import json
import random
from pathlib import Path

import markdown
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, CONTACT_PATH
from app.database import db_session, row_to_dict, rows_to_list

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _asset_url(path: str) -> str:
    """给静态资源路径追加基于文件修改时间的版本号, 用于强制浏览器刷新缓存。

    模板中用法: <img src="{{ asset_url('/static/img/logo.png') }}">
    文件改动后 mtime 变化 -> 版本号变化 -> 浏览器自动重新下载, 无需手动 bump。
    """
    import os
    rel = path
    if rel.startswith("/static/"):
        rel = rel[len("/static/"):]
    elif rel.startswith("static/"):
        rel = rel[len("static/"):]
    full = BASE_DIR / "static" / rel
    try:
        mtime = int(os.path.getmtime(full))
    except OSError:
        return path
    return f"{path}?v={mtime}"


templates.env.globals["asset_url"] = _asset_url


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
        raw_cases = rows_to_list(
            conn.execute(
                "SELECT * FROM cases WHERE is_online = 1 ORDER BY sort_order, id DESC"
            ).fetchall()
        )
        client_logos = rows_to_list(
            conn.execute(
                "SELECT * FROM site_client_logos WHERE is_visible = 1 ORDER BY sort_order"
            ).fetchall()
        )

    # 案例展示的「大小节奏」：18 项固定序列（6 竖 / 6 宽 / 6 方），相邻错开 → 排版节奏稳定。
    # 案例不足 18 张时的对策：循环复用真实案例，保证「大小节奏」与「无缝滚动所需内容量」不变；
    # 若库里完全没有在线案例，则用占位卡填满（不显示真实图片，但排版节奏一致）。
    CASE_SIZE_RHYTHM = [
        'portrait', 'wide', 'square', 'wide', 'portrait', 'square',
        'square', 'wide', 'portrait', 'portrait', 'square', 'wide',
        'portrait', 'square', 'wide', 'wide', 'square', 'portrait',
    ]
    MIN_CASES_PER_UNIT = 18  # 一个循环单元的最少卡片数（不足则循环复用）

    if raw_cases:
        unit_cases = []
        i = 0
        while len(unit_cases) < MIN_CASES_PER_UNIT:
            src = raw_cases[i % len(raw_cases)]
            c = dict(src)                       # 复制，避免污染原始列表
            c["size"] = CASE_SIZE_RHYTHM[i % len(CASE_SIZE_RHYTHM)]
            unit_cases.append(c)
            i += 1
    else:
        unit_cases = [
            {"id": 0, "title": "敬请期待", "cover_image": "", "size": s, "placeholder": True}
            for s in CASE_SIZE_RHYTHM
        ]

    return templates.TemplateResponse(
        "public/index.html",
        {
            "request": request,
            "studio": get_studio_profile(),
            "cases": unit_cases,            # 一个单元（模板渲染两遍 → 无缝循环）
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
        "public/projects.html",
        {
            "request": request,
            "studio": get_studio_profile(),
            "cases": cases,
            "contact": load_contact(),
        },
    )


@router.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    with db_session() as conn:
        cases = rows_to_list(
            conn.execute(
                "SELECT * FROM cases WHERE is_online = 1 ORDER BY sort_order, id DESC"
            ).fetchall()
        )
    return templates.TemplateResponse(
        "public/projects.html",
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
        prev_case = row_to_dict(
            conn.execute(
                "SELECT id, title FROM cases WHERE is_online = 1 AND id < ? ORDER BY id DESC LIMIT 1",
                (case["id"],),
            ).fetchone()
        )
        next_case = row_to_dict(
            conn.execute(
                "SELECT id, title FROM cases WHERE is_online = 1 AND id > ? ORDER BY id ASC LIMIT 1",
                (case["id"],),
            ).fetchone()
        )
    return templates.TemplateResponse(
        "public/project_detail.html",
        {
            "request": request,
            "studio": get_studio_profile(),
            "case": case,
            "images": images,
            "prev_case": prev_case,
            "next_case": next_case,
            "contact": load_contact(),
        },
    )


@router.get("/projects/{case_id}", response_class=HTMLResponse)
async def project_detail(request: Request, case_id: int):
    with db_session() as conn:
        case = row_to_dict(
            conn.execute(
                "SELECT * FROM cases WHERE id = ? AND is_online = 1", (case_id,)
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
        prev_case = row_to_dict(
            conn.execute(
                "SELECT id, title FROM cases WHERE is_online = 1 AND id < ? ORDER BY id DESC LIMIT 1",
                (case["id"],),
            ).fetchone()
        )
        next_case = row_to_dict(
            conn.execute(
                "SELECT id, title FROM cases WHERE is_online = 1 AND id > ? ORDER BY id ASC LIMIT 1",
                (case["id"],),
            ).fetchone()
        )
    return templates.TemplateResponse(
        "public/project_detail.html",
        {
            "request": request,
            "studio": get_studio_profile(),
            "case": case,
            "images": images,
            "prev_case": prev_case,
            "next_case": next_case,
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


@router.get("/news", response_class=HTMLResponse)
async def news(request: Request):
    notes = [
        {
            "date": "2026.07",
            "title": "某品牌零售空间动线升级",
            "summary": "为连锁零售品牌重构人流动线，将主通道宽度从 1.2m 调整至 1.8m，配合灯光分区，使核心货架停留率提升约 40%。",
            "img": "news-01.svg",
            "tag": "项目",
        },
        {
            "date": "2026.06",
            "title": "「岛式美陈系统」入选本地商业空间观察",
            "summary": "以模块化岛台为核心的可拆卸美陈系统，适配商场中庭快闪场景，15 天搭建、3 天撤场，被本地设计媒体收录报道。",
            "img": "news-02.svg",
            "tag": "动态",
        },
        {
            "date": "2026.05",
            "title": "团队参加空间与零售体验设计分享会",
            "summary": "作为嘉宾分享「从动线到材质：工装空间的设计决策链」，并与到场品牌方就餐饮空间体验升级进行圆桌讨论。",
            "img": "news-03.svg",
            "tag": "活动",
        },
    ]
    return templates.TemplateResponse(
        "public/news.html",
        {
            "request": request,
            "studio": get_studio_profile(),
            "notes": notes,
            "contact": load_contact(),
        },
    )
