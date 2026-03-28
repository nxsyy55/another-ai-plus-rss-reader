from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .routes import feeds, articles, settings, stats

app = FastAPI(title="aiNewReader Dashboard", docs_url=None, redoc_url=None)

# Mount routes
app.include_router(feeds.router, prefix="/feeds", tags=["feeds"])
app.include_router(articles.router, prefix="/articles", tags=["articles"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])

templates = Jinja2Templates(directory="templates/dashboard")


def _provider_status() -> dict:
    """Check which providers have API keys configured."""
    import httpx
    status = {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
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
    import json
    from datetime import datetime
    from aiNewReader.db import get_db, get_last_run, get_all_feeds, get_latest_report

    with get_db() as conn:
        last_run_row = get_last_run(conn)
        last_run = dict(last_run_row) if last_run_row else None
        feeds_all = get_all_feeds(conn)
        report_row = get_latest_report(conn)

    report = None
    if report_row:
        try:
            report = json.loads(report_row["content"])
        except Exception:
            pass

    report_date = datetime.utcnow().strftime("%Y-%m-%d")
    if last_run and last_run.get("started_at"):
        report_date = last_run["started_at"][:10]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "last_run": last_run,
        "total_feeds": len(feeds_all),
        "report": report,
        "report_date": report_date,
    })
