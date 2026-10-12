from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.routers import admin, api, auth, pages

settings = get_settings()

app = FastAPI(title="MTPI User Profiles", version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=settings.app_secret_key, https_only=False)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(pages.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(api.router)


@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}
