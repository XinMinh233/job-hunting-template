from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import text

from . import admin, auth, chats, deepseek_proxy, files
from .config import settings
from .db import engine, init_db
from .jobs import job_manager
from .runner_client import RunnerError, runner_client

PACKAGE_ROOT = Path(__file__).resolve().parent
templates = Environment(
    loader=FileSystemLoader(PACKAGE_ROOT / "templates"),
    autoescape=select_autoescape(("html", "xml")),
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    await job_manager.start()
    yield
    await job_manager.close()


app = FastAPI(
    title=settings.app_name,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.mount(
    "/static",
    StaticFiles(directory=PACKAGE_ROOT / "static"),
    name="static",
)
app.include_router(auth.router)
app.include_router(chats.router)
app.include_router(files.router)
app.include_router(admin.router)
app.include_router(deepseek_proxy.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; frame-src 'self'",
    )
    return response


def _page(name: str, request: Request, **context) -> HTMLResponse:
    html = templates.get_template(name).render(
        request=request,
        app_name=settings.app_name,
        **context,
    )
    return HTMLResponse(html)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return _page("login.html", request)


@app.get("/password", response_class=HTMLResponse)
def password_page(request: Request):
    return _page("password.html", request)


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return _page("admin.html", request)


@app.get("/", response_class=HTMLResponse)
def workspace_page(request: Request):
    return _page("app.html", request)


@app.get("/files/preview", response_class=HTMLResponse)
def markdown_preview_page(request: Request):
    return _page("preview.html", request)


@app.get("/healthz")
async def health():
    checks: dict[str, dict] = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": str(exc)[:200]}
    try:
        runner = await runner_client.request("health")
        runner_version = str(runner.get("claude_version") or "")
        runner_ok = bool(runner_version) and (
            not settings.claude_version
            or settings.claude_version in runner_version
        ) and (
            runner.get("primary_model") == settings.primary_model
            and runner.get("light_model") == settings.light_model
            and runner.get("effort_level") == settings.effort_level
        )
        checks["runner"] = {**runner, "ok": runner_ok}
    except RunnerError as exc:
        checks["runner"] = {"ok": False, "error": str(exc)[:200]}
    try:
        usage = shutil.disk_usage(settings.template_root)
        checks["disk"] = {
            "ok": usage.free >= 2 * 1024**3,
            "free_bytes": usage.free,
        }
    except OSError as exc:
        checks["disk"] = {"ok": False, "error": str(exc)[:200]}
    deepseek_url = urlparse(settings.deepseek_base_url)
    proxy_configured = bool(
        settings.deepseek_api_key
        and deepseek_url.scheme == "https"
        and deepseek_url.hostname
        and not deepseek_url.username
        and not deepseek_url.password
    )
    checks["deepseek_proxy"] = {
        "ok": proxy_configured,
        "configured": bool(settings.deepseek_api_key),
        "upstream_https": deepseek_url.scheme == "https",
    }
    try:
        ZoneInfo(settings.quota_timezone)
        timezone_ok = True
    except ZoneInfoNotFoundError:
        timezone_ok = False
    checks["configuration"] = {
        "ok": (
            not settings.is_development_secret
            and settings.cookie_secure
            and settings.public_base_url.startswith("https://")
            and bool(settings.claude_version)
            and settings.effort_level in {"low", "medium", "high", "max"}
            and timezone_ok
        ),
        "development_secret": settings.is_development_secret,
        "claude_version_pinned": bool(settings.claude_version),
        "effort_level_valid": (
            settings.effort_level in {"low", "medium", "high", "max"}
        ),
        "quota_timezone_valid": timezone_ok,
    }
    ok = all(item["ok"] for item in checks.values())
    return JSONResponse(
        {"ok": ok, "checks": checks},
        status_code=200 if ok else 503,
    )


@app.exception_handler(404)
async def not_found(_request: Request, _exc):
    return JSONResponse({"detail": "页面或接口不存在"}, status_code=404)


def run() -> None:
    uvicorn.run(
        "webapp.main:app",
        host="127.0.0.1",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
