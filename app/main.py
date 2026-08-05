from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import BASE_DIR
from app.routers import app_auth, app_dashboard, library, projects, public, quotes, settings

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
app.include_router(projects.router)
app.include_router(library.router)
app.include_router(quotes.router)
app.include_router(settings.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
