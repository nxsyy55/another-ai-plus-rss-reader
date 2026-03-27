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
    import os
    import httpx as _httpx
    from aiNewReader.config import get_config
    from aiNewReader.db import get_db, get_all_feeds

    cfg = get_config()
    with get_db() as conn:
        feeds_all = get_all_feeds(conn)

    provider_status = {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
        "deepseek": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "ollama": False,
    }
    try:
        with _httpx.Client(timeout=2.0) as client:
            r = client.get(f"{cfg.provider.ollama_base_url}/api/tags")
            provider_status["ollama"] = r.status_code == 200
    except Exception:
        pass

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "cfg": cfg,
        "provider_status": provider_status,
    })


@router.post("/save")
async def save_settings(
    request: Request,
    hours_window: int = Form(24),
    max_articles_per_run: int = Form(300),
    provider_default: str = Form("anthropic"),
    anthropic_model: str = Form("claude-sonnet-4-6"),
    gemini_model: str = Form("gemini-3.1-pro-preview"),
    ollama_base_url: str = Form("http://localhost:11434"),
    ollama_embed_model: str = Form("bge-m3"),
    ollama_chat_model: str = Form("qwen3.5:9b"),
    deepseek_model: str = Form("deepseek-chat"),
):
    with open("config.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    data["hours_window"] = hours_window
    data["max_articles_per_run"] = max_articles_per_run
    if data.get("provider") is None:
        data["provider"] = {}
    data["provider"]["default"] = provider_default
    data["provider"]["anthropic_model"] = anthropic_model
    data["provider"]["gemini_model"] = gemini_model
    data["provider"]["ollama_base_url"] = ollama_base_url
    data["provider"]["ollama_embed_model"] = ollama_embed_model
    data["provider"]["ollama_chat_model"] = ollama_chat_model
    data["provider"]["deepseek_model"] = deepseek_model

    # Cleanup old fields if they exist in yaml
    for k in ["classify_model", "audit_model", "gemini_classify_model", "gemini_audit_model", "deepseek_classify_model", "deepseek_audit_model"]:
        data["provider"].pop(k, None)
    data.pop("audit_word_threshold", None)

    with open("config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    load_config("config.yaml")
    return RedirectResponse(url="/", status_code=303)
