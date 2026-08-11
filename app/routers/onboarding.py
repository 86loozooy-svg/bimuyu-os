"""新手引导偏好：标记完成/跳过，以及设置页召回（重置）。

任意登录用户可写自己的 onboarding_done 标记。
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth import get_current_user
from app.database import db_session

router = APIRouter(prefix="/app/onboarding", tags=["onboarding"])


@router.post("/dismiss")
async def dismiss_onboarding(user: dict = Depends(get_current_user)):
    with db_session() as conn:
        conn.execute(
            "UPDATE collaborators SET onboarding_done = 1 WHERE id = ?", (user["id"],)
        )
    return JSONResponse({"ok": True})


@router.post("/reset")
async def reset_onboarding(user: dict = Depends(get_current_user)):
    """设置页召回：把引导状态重置为未完成，前端随后重放。"""
    with db_session() as conn:
        conn.execute(
            "UPDATE collaborators SET onboarding_done = 0 WHERE id = ?", (user["id"],)
        )
    return JSONResponse({"ok": True})
