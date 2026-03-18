from __future__ import annotations

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


@app.get("/")
async def index(request: Request):
    from aiNewReader.db import get_db, get_last_run, get_all_feeds
    from aiNewReader.config import get_config

    with get_db() as conn:
        last_run = get_last_run(conn)
        feeds_all = get_all_feeds(conn)

    healthy = sum(1 for f in feeds_all if f["healthy"])
    unhealthy = len(feeds_all) - healthy

    return templates.TemplateResponse("index.html", {
        "request": request,
        "last_run": dict(last_run) if last_run else None,
        "total_feeds": len(feeds_all),
        "healthy_feeds": healthy,
        "unhealthy_feeds": unhealthy,
    })
