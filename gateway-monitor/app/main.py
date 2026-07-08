import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.database import is_database_connected
from app.logging_config import configure_logging
from app.routers import api, auth, health, websocket
from app.services.auth import get_current_user
from app.services.monitoring import (
    asterisk_ami_monitor,
    event_backup_service,
    gateway_line_monitor,
)

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s %s", settings.app_name, settings.app_version)
    asterisk_ami_monitor.start()
    gateway_line_monitor.start()
    event_backup_service.start()
    try:
        yield
    finally:
        await asterisk_ami_monitor.stop()
        await gateway_line_monitor.stop()
        await event_backup_service.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(api.router, prefix="/api")
app.include_router(websocket.router)
app.add_api_route("/metrics", api.prometheus_metrics, methods=["GET"])


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    current_user = get_current_user(request)
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    now = datetime.now(ZoneInfo(settings.timezone))
    database_connected = is_database_connected()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "status": "Servidor Online",
            "database_status": "Banco conectado"
            if database_connected
            else "Banco indisponivel",
            "current_date": now.strftime("%d/%m/%Y"),
            "current_time": now.strftime("%H:%M:%S"),
            "version": settings.app_version,
            "current_user": current_user,
            "grafana_url": settings.grafana_url,
            "lines_snapshot": gateway_line_monitor.snapshot,
            "asterisk_snapshot": asterisk_ami_monitor.snapshot,
        },
    )


@app.get("/tv", response_class=HTMLResponse)
def tv_dashboard(request: Request) -> HTMLResponse:
    now = datetime.now(ZoneInfo(settings.timezone))
    database_connected = is_database_connected()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "status": "Servidor Online",
            "database_status": "Banco conectado"
            if database_connected
            else "Banco indisponivel",
            "current_date": now.strftime("%d/%m/%Y"),
            "current_time": now.strftime("%H:%M:%S"),
            "version": settings.app_version,
            "current_user": "tv",
            "grafana_url": settings.grafana_url,
            "lines_snapshot": gateway_line_monitor.snapshot,
            "asterisk_snapshot": asterisk_ami_monitor.snapshot,
        },
    )


@app.get("/capacity", response_class=HTMLResponse)
def capacity_dashboard(request: Request) -> HTMLResponse:
    current_user = get_current_user(request)
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    now = datetime.now(ZoneInfo(settings.timezone))
    return templates.TemplateResponse(
        "capacity.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "current_date": now.strftime("%d/%m/%Y"),
            "current_time": now.strftime("%H:%M:%S"),
            "version": settings.app_version,
            "trunk_sips": settings.capacity_trunk_sip_list,
            "line_count": settings.capacity_line_count,
        },
    )
