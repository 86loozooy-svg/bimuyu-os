from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import BASE_DIR
from app.routers import account, app_auth, app_dashboard, budget, calculator, catalog, cost_estimate, library, notifications, onboarding, placeholders, projects, public, quotes, settings, share, tasks, workers

app = FastAPI(title="Studio OS", version="1.0.0", docs_url=None, redoc_url=None)

static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve case images from data/public
public_data = BASE_DIR / "data" / "public"
public_data.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(BASE_DIR / "data")), name="media")


class AppAuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated users away from /app/* (except login & invite)."""

    PUBLIC_PATHS = {"/app/login", "/app/accept-invite"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/app") and path not in self.PUBLIC_PATHS:
            if not path.startswith("/app/login") and request.method == "GET":
                from app.auth import decode_token
                from app.config import COOKIE_NAME

                token = request.cookies.get(COOKIE_NAME)
                if not token or not decode_token(token):
                    return RedirectResponse(url="/app/login", status_code=303)
        return await call_next(request)


app.add_middleware(AppAuthMiddleware)

app.include_router(public.router)
app.include_router(app_auth.router)
app.include_router(app_dashboard.router)
app.include_router(app_dashboard.router_root)
app.include_router(projects.router)
app.include_router(library.router)
app.include_router(quotes.router)
app.include_router(catalog.router)
app.include_router(calculator.router)
app.include_router(cost_estimate.router)
app.include_router(budget.router)
app.include_router(settings.router)
app.include_router(workers.router)
app.include_router(tasks.router)
app.include_router(notifications.router)
app.include_router(placeholders.router)
app.include_router(share.router)
app.include_router(share.public_router)
app.include_router(onboarding.router)
app.include_router(account.router)


@app.on_event("startup")
def _startup_ensure_schema() -> None:
    """启动时幂等建表 + 补齐 account 列，确保旧库一启动就拥有全部表结构。"""
    try:
        from app.init_db import init_schema

        init_schema()
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("uvicorn.error").warning("建表跳过: %s", exc)
    try:
        from app.routers import settings as _settings

        _settings._ensure_account_columns()
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("uvicorn.error").warning("账号列迁移跳过: %s", exc)
    try:
        from app.init_db import ensure_cases_columns

        ensure_cases_columns()
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("uvicorn.error").warning("cases 列迁移跳过: %s", exc)
    try:
        from app.init_db import ensure_pnl_columns

        ensure_pnl_columns()
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("uvicorn.error").warning("P&L 列迁移跳过: %s", exc)
    try:
        from app.init_db import ensure_notifications

        ensure_notifications()
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("uvicorn.error").warning("通知表迁移跳过: %s", exc)
    try:
        from app.init_db import _migrate_schema

        _migrate_schema()
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("uvicorn.error").warning("迁移脚本跳过: %s", exc)
    _startup_scheduler()


def _startup_scheduler() -> None:
    """启动 APScheduler：每日按 notify_push_time（默认 08:00）扫描到期待办并推送。"""
    try:
        import atexit
        import logging

        from apscheduler.schedulers.background import BackgroundScheduler

        from app.database import db_session
        from app.services import push

        hour, minute = 8, 0
        try:
            with db_session() as conn:
                row = conn.execute(
                    "SELECT value FROM site_config WHERE key = 'notify_push_time'"
                ).fetchone()
                if row and row["value"]:
                    hh, mm = str(row["value"]).split(":")
                    hour, minute = int(hh), int(mm)
        except Exception:
            pass
        sched = BackgroundScheduler()
        sched.add_job(
            push.scan_and_push, "cron", hour=hour, minute=minute, id="daily_task_push"
        )
        # P0：每日凌晨 03:00 重算全部项目损益派生字段（落库，降低前端复杂度）
        from app.services import pnl as pnl_service

        sched.add_job(
            pnl_service.recalc_all, "cron", hour=3, minute=0, id="daily_pnl_recalc"
        )
        # P3：每日 09:00 扫描未来 7 天到期未付发票，推送站内通知
        from app.services import notifications as notif_service

        sched.add_job(
            notif_service.scan_invoice_due,
            "cron",
            hour=9,
            minute=0,
            id="daily_invoice_due_scan",
        )
        sched.start()
        logging.getLogger("uvicorn.error").info(
            "调度器已启动：每日 %02d:%02d 扫描待办推送；03:00 重算项目损益", hour, minute
        )
        atexit.register(lambda: sched.shutdown(wait=False))
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("uvicorn.error").warning("调度器启动跳过: %s", exc)


@app.get("/health")
async def health():
    return {"status": "ok"}
