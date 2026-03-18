from __future__ import annotations

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import yaml

from aiNewReader.config import get_config, load_config

router = APIRouter()
templates = Jinja2Templates(directory="templates/dashboard")


@router.get("/", response_class=HTMLResponse)
async def settings_page(request: Request):
    cfg = get_config()
    return templates.TemplateResponse("settings.html", {"request": request, "cfg": cfg})


@router.post("/save")
async def save_settings(
    request: Request,
    hours_window: int = Form(24),
    audit_word_threshold: int = Form(500),
    max_articles_per_run: int = Form(300),
    provider_default: str = Form("anthropic"),
    classify_model: str = Form("claude-haiku-4-5-20251001"),
    audit_model: str = Form("claude-sonnet-4-6"),
):
    # Read current config
    with open("config.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    data["hours_window"] = hours_window
    data["audit_word_threshold"] = audit_word_threshold
    data["max_articles_per_run"] = max_articles_per_run
    data.setdefault("provider", {})
    data["provider"]["default"] = provider_default
    data["provider"]["classify_model"] = classify_model
    data["provider"]["audit_model"] = audit_model

    with open("config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    load_config("config.yaml")
    return RedirectResponse(url="/settings/", status_code=303)
