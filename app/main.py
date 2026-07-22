from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.router import router as api_router
from app.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")

# ── API routes ─────────────────────────────────────────────────────────
app.include_router(api_router)

# ── Static files ───────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# ── Templates ──────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Jinja2 3.1.6 LRUCache has a compatibility issue with Python 3.14
# where weakrefs in cache keys can trigger unhashable-type errors.
# Disabling template caching entirely avoids the problem.
templates.env.cache = None


# ── Frontend routes ────────────────────────────────────────────────────


@app.get("/", tags=["frontend"])
@app.get("/landing", tags=["frontend"], include_in_schema=False)
async def landing(request: Request):
    """Demo landing / marketing page."""
    return templates.TemplateResponse(
        request,
        "landing.html",
        {"env": settings.app_env},
    )


@app.get("/dashboard", tags=["frontend"])
async def dashboard(request: Request):
    """Mission Control Dashboard."""
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"env": settings.app_env},
    )


@app.get("/leads", tags=["frontend"])
async def leads_list(request: Request):
    """Lead intelligence list view."""
    return templates.TemplateResponse(
        request,
        "leads.html",
        {"active_nav": "leads", "env": settings.app_env},
    )


@app.get("/leads/{lead_id}", tags=["frontend"])
async def lead_detail(request: Request, lead_id: str):
    """Single lead detail view."""
    return templates.TemplateResponse(
        request,
        "lead_detail.html",
        {"active_nav": "leads", "lead_id": lead_id, "env": settings.app_env},
    )


@app.get("/outreach", tags=["frontend"])
async def outreach_view(request: Request):
    """Outreach drafts queue view."""
    return templates.TemplateResponse(
        request,
        "outreach.html",
        {"active_nav": "outreach", "env": settings.app_env},
    )


@app.get("/pipeline", tags=["frontend"])
async def pipeline_view(request: Request):
    """Pipeline Kanban view."""
    return templates.TemplateResponse(
        request,
        "pipeline.html",
        {"active_nav": "pipeline", "env": settings.app_env},
    )


@app.get("/inbound", tags=["frontend"])
async def inbound_view(request: Request):
    """Inbound message queue view."""
    return templates.TemplateResponse(
        request,
        "inbound.html",
        {"active_nav": "inbound", "env": settings.app_env},
    )


@app.get("/activity", tags=["frontend"])
async def activity_view(request: Request):
    """Agent activity / task log view."""
    return templates.TemplateResponse(
        request,
        "activity.html",
        {"active_nav": "activity", "env": settings.app_env},
    )


# ── Health ─────────────────────────────────────────────────────────────


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Minimal liveness endpoint; database readiness belongs to a later check."""
    return {"status": "ok", "environment": settings.app_env}
