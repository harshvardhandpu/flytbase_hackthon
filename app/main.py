import subprocess
import sys
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


# ── Demo Mode ─────────────────────────────────────────────────────────


@app.get("/demo", tags=["frontend"])
async def demo_page(request: Request):
    """One-click judge demonstration page.

    Opens a demo introduction screen. The 'Launch Demo Mission' button
    seeds demo data and redirects to the Mission Control dashboard.
    """
    return templates.TemplateResponse(
        request,
        "demo.html",
        {"env": settings.app_env},
    )


@app.post("/demo/seed", tags=["frontend"])
async def demo_seed() -> dict[str, str]:
    """Seed demo data and return redirect URL.

    Called by the Launch Demo Mission button. Runs the seed script
    then returns the dashboard URL for the frontend to navigate to.
    """
    try:
        seed_script = (
            Path(__file__).resolve().parent.parent / "scripts" / "seed_demo_data.py"
        )
        result = subprocess.run(
            [sys.executable, str(seed_script)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {
                "status": "error",
                "message": result.stderr[:500],
                "redirect": "/dashboard",
            }
        return {
            "status": "ok",
            "message": "Demo data seeded successfully",
            "redirect": "/dashboard",
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc)[:500],
            "redirect": "/dashboard",
        }


# ── Health ─────────────────────────────────────────────────────────────


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Minimal liveness endpoint; database readiness belongs to a later check."""
    return {"status": "ok", "environment": settings.app_env}
