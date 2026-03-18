from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import feeds, filters, articles, settings

app = FastAPI(title="aiNewReader Dashboard", docs_url=None, redoc_url=None)

# Mount routes
app.include_router(feeds.router, prefix="/feeds", tags=["feeds"])
app.include_router(filters.router, prefix="/filters", tags=["filters"])
app.include_router(articles.router, prefix="/articles", tags=["articles"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])

templates = Jinja2Templates(directory="templates/dashboard")


def _provider_status() -> dict:
    """Check which providers have API keys configured."""
    import httpx
    status = {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
        "deepseek": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "ollama": False,
    }
    # Quick ping Ollama
    from aiNewReader.config import get_config
    try:
        base_url = get_config().provider.ollama_base_url
        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{base_url}/api/tags")
            status["ollama"] = r.status_code == 200
    except Exception:
        pass
    return status


@app.get("/")
async def index(request: Request):
    from aiNewReader.db import get_db, get_last_run, get_all_feeds
    from aiNewReader.config import get_config

    with get_db() as conn:
        last_run = dict(get_last_run(conn)) if get_last_run(conn) else None
        feeds_all = get_all_feeds(conn)

    healthy = sum(1 for f in feeds_all if f["healthy"])
    unhealthy = len(feeds_all) - healthy

    cfg = get_config()
    provider_status = _provider_status()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "last_run": last_run,
        "total_feeds": len(feeds_all),
        "healthy_feeds": healthy,
        "unhealthy_feeds": unhealthy,
        "cfg": cfg,
        "provider_status": provider_status,
    })
