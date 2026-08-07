"""智能造价预估模块。

- GET  /api/cost-estimate        返回配置（业态/城市/旧改/材质分组/服务范围/历史样本/AI开关）
- POST /api/cost-estimate        规则引擎：纯计算，返回低/中/高三档 + breakdown
- POST /ai/chat                  AI 文案解释（可选，默认关），SiliconFlow DeepSeek-V3 SSE 流式
- GET  /app/calculator/cost-estimate   前端 Stepper 页面
- GET  /app/settings/ai-cost     AI 解释开关设置页
- POST /app/settings/ai-cost     保存开关
- POST /app/projects/{id}/mark-cost-sample  标记完工项目为历史造价样本

数字准确性以规则引擎为准，AI 绝不参与运算。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_current_user, require_admin, user_can_access_project
from app.config import BASE_DIR, DATA_DIR
from app.database import db_session, row_to_dict

router = APIRouter(tags=["cost-estimate"])
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

COST_BASE_PATH = BASE_DIR / "static" / "data" / "cost_base.json"
HISTORY_PATH = DATA_DIR / "cost_history.json"

# 非材质类顶级 key，前端构建材质多选时需排除
_NON_MATERIAL_KEYS = {
    "version", "meta", "categories", "city_tiers", "old_renovation",
    "floor_height", "zone_complexity", "service_scope",
}


# ── 数据读取 ───────────────────────────────────────────────────────────────
def load_cost_base() -> dict:
    if not COST_BASE_PATH.exists():
        return {}
    return json.loads(COST_BASE_PATH.read_text(encoding="utf-8"))


def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return data.get("samples", [])
    except Exception:
        return []


def save_history(samples: list) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps({"samples": samples}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_site_config_value(key: str, default: str = "") -> str:
    try:
        with db_session() as conn:
            row = conn.execute(
                "SELECT value FROM site_config WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else default
    except Exception:
        return default


def set_site_config_value(key: str, value: str) -> None:
    with db_session() as conn:
        cur = conn.execute(
            "UPDATE site_config SET value = ? WHERE key = ?", (value, key)
        )
        if cur.rowcount == 0:
            conn.execute(
                "INSERT INTO site_config (key, value) VALUES (?, ?)", (key, value)
            )


def is_ai_enabled() -> bool:
    """开关打开 且 已配置 SILICONFLOW_KEY 才视为可用。"""
    if not os.environ.get("SILICONFLOW_KEY"):
        return False
    return get_site_config_value("ai_cost_explanation_enabled", "0") == "1"


# ── 配置端点 ───────────────────────────────────────────────────────────────
@router.get("/api/cost-estimate")
async def cost_estimate_config(user: dict = Depends(get_current_user)):
    base = load_cost_base()
    cats = base.get("categories", {})
    materials = {
        k: list(v.keys())
        for k, v in base.items()
        if k not in _NON_MATERIAL_KEYS and isinstance(v, dict)
    }
    history = [
        {
            "id": h.get("id"),
            "type": h.get("type"),
            "area": h.get("area"),
            "actual_per_sqm": h.get("actual_per_sqm"),
            "project_name": h.get("project_name"),
            "created_at": h.get("created_at"),
        }
        for h in load_history()
    ]
    return JSONResponse(
        {
            "types": list(cats.keys()),
            "type_labels": {k: v.get("label", k) for k, v in cats.items()},
            "city_tiers": list(base.get("city_tiers", {}).keys()),
            "old_statuses": list(base.get("old_renovation", {}).keys()),
            "service_scopes": list(base.get("service_scope", {}).keys()),
            "material_groups": materials,
            "floor_base_m": base.get("floor_height", {}).get("base_m", 3.5),
            "history": history,
            "ai_enabled": is_ai_enabled(),
        }
    )


# ── 规则引擎 ───────────────────────────────────────────────────────────────
def run_estimate(survey: dict, base: dict, history: list) -> dict:
    cat = (survey.get("type") or "").strip()
    area = float(survey.get("area") or 0)
    city = (survey.get("city_tier") or "").strip()
    old = (survey.get("old_status") or "").strip()
    fh = float(survey.get("floor_height") or base.get("floor_height", {}).get("base_m", 3.5))
    zones = survey.get("zones") or []
    materials = survey.get("materials") or {}
    scope = (survey.get("service_scope") or "").strip()

    cats = base.get("categories", {})

    # 1) 基准单平米：优先匹配同 type 最近 3 条历史，否则回落 base
    same_type = [h for h in history if (h.get("type") or "") == cat]
    same_type.sort(key=lambda h: h.get("created_at", ""), reverse=True)
    recent3 = same_type[:3]
    if recent3:
        base_per_sqm = sum(float(h.get("actual_per_sqm", 0)) for h in recent3) / len(recent3)
        base_source = "history"
        history_used = [
            {
                "id": h.get("id"),
                "type": h.get("type"),
                "area": h.get("area"),
                "actual_per_sqm": h.get("actual_per_sqm"),
                "project_name": h.get("project_name"),
                "created_at": h.get("created_at"),
            }
            for h in recent3
        ]
    else:
        base_per_sqm = (cats.get(cat) or cats.get("其他", {})).get("base_per_sqm", 0)
        base_source = "base"
        history_used = []

    # 2) 乘子
    city_mult = base.get("city_tiers", {}).get(city, 1.0)
    old_mult = base.get("old_renovation", {}).get(old, 1.0)
    fh_cfg = base.get("floor_height", {})
    fh_factor = 1 + max(0.0, fh - fh_cfg.get("base_m", 3.5)) * fh_cfg.get("per_extra_meter", 0.04)
    zc = base.get("zone_complexity", {})
    nzones = len([z for z in zones if (z or {}).get("name")])
    zone_factor = min(1 + max(0, nzones - 1) * zc.get("per_extra_zone", 0.015), zc.get("cap", 1.10))

    # 3) 材质/设备每平米加价（多选求和）
    mat_detail: dict = {}
    mat_per_sqm = 0.0
    for cat_key, opts in materials.items():
        for opt in (opts or []):
            v = base.get(cat_key, {}).get(opt)
            if isinstance(v, (int, float)):
                mat_per_sqm += float(v)
                mat_detail.setdefault(cat_key, {})[opt] = float(v)

    service_cov = base.get("service_scope", {}).get(scope, 1.0)
    low_mult = base.get("meta", {}).get("low_mult", 0.82)
    high_mult = base.get("meta", {}).get("high_mult", 1.25)

    # 4) 中档总价 = (基准×城市×旧改×层高×分区 + 材质) × 面积 × 服务覆盖
    mid_gross = base_per_sqm * city_mult * old_mult * fh_factor * zone_factor + mat_per_sqm
    mid_total = mid_gross * area * service_cov
    low_total = mid_total * low_mult
    high_total = mid_total * high_mult

    low_ps = low_total / area if area else 0
    mid_ps = mid_total / area if area else 0
    high_ps = high_total / area if area else 0

    tiers = {
        "low": {"total": round(low_total), "per_sqm": round(low_ps)},
        "mid": {"total": round(mid_total), "per_sqm": round(mid_ps)},
        "high": {"total": round(high_total), "per_sqm": round(high_ps)},
    }
    breakdown = {
        "base_per_sqm": round(base_per_sqm, 2),
        "base_source": base_source,
        "history_used": history_used,
        "city_mult": city_mult,
        "old_mult": old_mult,
        "fh_factor": round(fh_factor, 4),
        "floor_height_input_m": fh,
        "zone_factor": round(zone_factor, 4),
        "zone_count": nzones,
        "materials": mat_detail,
        "mat_per_sqm": round(mat_per_sqm, 2),
        "service_cov": service_cov,
        "mid_gross_per_sqm": round(mid_gross, 2),
        "low_mult": low_mult,
        "high_mult": high_mult,
    }
    return {
        "type": cat,
        "city_tier": city,
        "area": area,
        "floor_height": fh,
        "old_status": old,
        "service_scope": scope,
        "zones": zones,
        "materials": materials,
        "tiers": tiers,
        "breakdown": breakdown,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@router.post("/api/cost-estimate")
async def cost_estimate_submit(request: Request, user: dict = Depends(get_current_user)):
    try:
        survey = await request.json()
    except Exception:
        return JSONResponse({"error": "请求体需为 JSON"}, status_code=400)

    if not (survey.get("type") and survey.get("area")):
        return JSONResponse({"error": "缺少必填项：类型 / 面积"}, status_code=400)
    try:
        float(survey.get("area"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "面积必须为数字"}, status_code=400)

    base = load_cost_base()
    history = load_history()
    result = run_estimate(survey, base, history)
    return JSONResponse(result)


# ── AI 文案解释（可选，默认关） ──────────────────────────────────────────────
SYSTEM_PROMPT = (
    "你是一名工程造价助理。你收到的项目造价调查摘要与三档预算数字（低/中/高）"
    "由规则引擎计算得出，数字权威、不可更改。请只生成 2-3 句中文解释，覆盖三点："
    "1）为什么高档预算更贵；2）主要成本变量是什么；3）旧改风险提示（如涉及）。"
    "要求：绝对不得修改、重新计算或质疑任何数字；不列出计算过程；不编造数据；"
    "语气专业、简洁、克制。"
)


def _build_user_prompt(survey: dict, tiers: dict) -> str:
    mat_flat = []
    for k, opts in (survey.get("materials") or {}).items():
        if opts:
            mat_flat.append(f"{k}:{','.join(opts)}")
    mat_str = "、".join(mat_flat) if mat_flat else "未选"
    return (
        f"项目类型：{survey.get('type')}；城市等级：{survey.get('city_tier')}；"
        f"面积：{survey.get('area')}㎡；层高：{survey.get('floor_height')}m；"
        f"旧改状态：{survey.get('old_status')}；主要材质/设备：{mat_str}；"
        f"服务范围：{survey.get('service_scope')}。\n"
        f"预算估算（规则引擎，权威数字）：低档 ¥{tiers['low']['total']}（单平米 ¥{tiers['low']['per_sqm']}），"
        f"中档 ¥{tiers['mid']['total']}（单平米 ¥{tiers['mid']['per_sqm']}），"
        f"高档 ¥{tiers['high']['total']}（单平米 ¥{tiers['high']['per_sqm']}）。请生成解释。"
    )


@router.post("/ai/chat")
async def ai_chat(request: Request, user: dict = Depends(get_current_user)):
    if not is_ai_enabled():
        return JSONResponse(
            {"error": "AI 解释未启用（需在设置开启开关并配置环境变量 SILICONFLOW_KEY）"},
            status_code=403,
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "请求体需为 JSON"}, status_code=400)

    survey = payload.get("survey", {})
    tiers = payload.get("tiers", {})
    if not tiers:
        return JSONResponse({"error": "缺少 tiers（三档数字）"}, status_code=400)

    user_prompt = _build_user_prompt(survey, tiers)
    api_key = os.environ["SILICONFLOW_KEY"]

    async def event_gen():
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    "https://api.siliconflow.cn/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "deepseek-ai/DeepSeek-V3",
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": True,
                        "max_tokens": 220,
                        "temperature": 0.6,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        err_text = await resp.aread()
                        try:
                            err_msg = err_text.decode("utf-8", "ignore")[:200]
                        except Exception:
                            err_msg = f"upstream {resp.status_code}"
                        yield f"data: {json.dumps({'error': f'AI 服务返回 {resp.status_code}：{err_msg}'}, ensure_ascii=False)}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data == "[DONE]":
                                yield "data: [DONE]\n\n"
                                break
                            try:
                                obj = json.loads(data)
                                delta = obj["choices"][0]["delta"].get("content", "")
                                if delta:
                                    yield f"data: {json.dumps({'token': delta}, ensure_ascii=False)}\n\n"
                            except Exception:
                                continue
        except Exception as e:  # 网络/密钥错误时给前端一个明确信号
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 前端页面 ───────────────────────────────────────────────────────────────
@router.get("/app/calculator/cost-estimate", response_class=HTMLResponse)
async def cost_estimate_page(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse(
        "app/calculator/cost_estimate.html",
        {"request": request, "user": user},
    )


# ── 设置：AI 解释开关 ──────────────────────────────────────────────────────
@router.get("/app/settings/ai-cost", response_class=HTMLResponse)
async def ai_cost_settings_page(request: Request, user: dict = Depends(require_admin)):
    enabled = get_site_config_value("ai_cost_explanation_enabled", "0") == "1"
    has_key = bool(os.environ.get("SILICONFLOW_KEY"))
    return templates.TemplateResponse(
        "app/settings/ai_cost.html",
        {"request": request, "user": user, "enabled": enabled, "has_key": has_key},
    )


@router.post("/app/settings/ai-cost")
async def ai_cost_settings_save(
    user: dict = Depends(require_admin), enabled: str = Form("")
):
    set_site_config_value("ai_cost_explanation_enabled", "1" if enabled == "on" else "0")
    return RedirectResponse("/app/settings/ai-cost", status_code=303)


# ── 历史库扩展：标记完工项目为造价样本 ─────────────────────────────────────
@router.post("/app/projects/{project_id}/mark-cost-sample")
async def mark_cost_sample(
    project_id: int,
    request: Request,
    user: dict = Depends(get_current_user),
    actual_total: float = Form(...),
    material_tags: str = Form(""),
):
    if not user_can_access_project(user, project_id):
        return JSONResponse({"error": "无权访问该项目"}, status_code=403)
    if user["role"] != "admin":
        return JSONResponse({"error": "仅管理员可标记历史造价样本"}, status_code=403)
    if actual_total <= 0:
        return RedirectResponse(
            f"/app/projects/{project_id}?tab=overview&mark_error=1", status_code=303
        )

    with db_session() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        project = row_to_dict(row)
    if not project:
        return JSONResponse({"error": "项目不存在"}, status_code=404)

    area = float(project.get("area") or 0)
    if area <= 0:
        return RedirectResponse(
            f"/app/projects/{project_id}?tab=overview&mark_error=area", status_code=303
        )

    per_sqm = actual_total / area
    tags = [t.strip() for t in (material_tags or "").split(",") if t.strip()]
    samples = load_history()
    new_id = (max([s.get("id", 0) for s in samples], default=0) + 1) if samples else 1
    samples.append(
        {
            "id": new_id,
            "type": project.get("industry") or "其他",
            "area": area,
            "actual_per_sqm": round(per_sqm, 2),
            "actual_total": round(actual_total, 2),
            "material_tags": tags,
            "project_id": project_id,
            "project_name": project.get("name"),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_history(samples)
    return RedirectResponse(
        f"/app/projects/{project_id}?tab=overview&marked=1", status_code=303
    )


# ── 造价 → 项目预算：把分项写入 project_budget_item 作为初始预算 ────────────
@router.post("/api/cost-estimate/save-to-budget")
async def save_estimate_to_budget(request: Request, user: dict = Depends(get_current_user)):
    """智能造价结果保存为项目初始预算。

    将中档总价拆解为「基础工程」+ 各材质分类分项，写入 project_budget_item。
    保存幂等：先清空该项目旧预算分项（关联开销 budget_item_id 置空、流水保留）。
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "请求体需为 JSON"}, status_code=400)

    try:
        project_id = int(payload.get("project_id"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "project_id 必填且为整数"}, status_code=400)
    survey = payload.get("survey", {})
    if not user_can_access_project(user, project_id):
        return JSONResponse({"error": "无权访问该项目"}, status_code=403)
    if user["role"] == "viewer":
        return JSONResponse({"error": "访客无编辑权限"}, status_code=403)
    if not (survey.get("type") and survey.get("area")):
        return JSONResponse({"error": "缺少造价调查（type/area）"}, status_code=400)

    base = load_cost_base()
    history = load_history()
    result = run_estimate(survey, base, history)
    tiers = result["tiers"]
    bd = result["breakdown"]
    area = float(result.get("area") or 0)
    service_cov = float(bd.get("service_cov", 1.0))

    base_part = (
        bd.get("base_per_sqm", 0)
        * bd.get("city_mult", 1.0)
        * bd.get("old_mult", 1.0)
        * bd.get("fh_factor", 1.0)
        * bd.get("zone_factor", 1.0)
        * area
        * service_cov
    )
    # 分项：基础工程 + 每个材质分类（按该分类加价和拆分）
    items = [("基础工程", "基础", round(base_part))]
    for cat_key, opts in (bd.get("materials") or {}).items():
        cat_sum = sum(float(v) for v in opts.values())
        planned = round(cat_sum * area * service_cov)
        if planned > 0:
            items.append((cat_key, cat_key, planned))

    with db_session() as conn:
        conn.execute(
            "UPDATE project_expense SET budget_item_id=NULL WHERE project_id=?", (project_id,)
        )
        conn.execute("DELETE FROM project_budget_item WHERE project_id=?", (project_id,))
        for idx, (name, category, planned) in enumerate(items, 1):
            conn.execute(
                "INSERT INTO project_budget_item (project_id, name, category, planned_amount, sort_order) "
                "VALUES (?,?,?,?,?)",
                (project_id, name, category, planned, idx),
            )

    return JSONResponse(
        {
            "ok": True,
            "items": len(items),
            "mid_total": tiers["mid"]["total"],
            "redirect": f"/app/projects/{project_id}?tab=overview",
        }
    )
