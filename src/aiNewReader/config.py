from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv(override=True)  # .env values always take priority over system env vars
from pydantic import BaseModel, Field


class EmailConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    to: str = ""


class TelegramConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class DeliveryConfig(BaseModel):
    markdown_output: str = "./output/digest-{date}.md"
    email: EmailConfig = Field(default_factory=EmailConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class ProviderConfig(BaseModel):
    default: str = "anthropic"
    anthropic_model: str = "claude-sonnet-4-6"
    gemini_model: str = "gemini-3.1-pro-preview"
    ollama_chat_model: str = "qwen3.5:9b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "bge-m3"


class DashboardConfig(BaseModel):
    port: int = 8080
    host: str = "localhost"


class HubConfig(BaseModel):
    enabled: bool = True
    path: str = "./hub"


_DEFAULT_REPORT_PROMPT = """You are a senior news analyst writing a concise daily briefing.
Given the scraped markdown text of today's articles,
produce a structured JSON report with these fields:
- "executive_summary": 2-3 paragraphs of flowing prose covering the major themes
- "key_themes": list of up to 5 objects, each with:
    - "theme": short label (3-6 words)
    - "insight": 1-2 sentence analysis
    - "articles": list of {title, url} for the 2-4 most relevant articles
- "notable_picks": list of up to 5 {title, url, reason} — standout articles worth reading

Write in the same language as the majority of articles. Be analytical, not just descriptive.
Return ONLY the JSON object, no markdown fences."""


class AppConfig(BaseModel):
    hours_window: int = 24
    max_articles_per_run: int = 300
    max_articles_per_source: int = 10
    health_check_interval_hours: int = 24
    # firecrawl_enabled: bool = True
    report_prompt: str = _DEFAULT_REPORT_PROMPT
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    hub: HubConfig = Field(default_factory=HubConfig)


_config: AppConfig | None = None
_config_path: Path | None = None


def load_config(path: Path | str | None = None) -> AppConfig:
    global _config, _config_path

    if path is None:
        path = Path(os.environ.get("AINEWREADER_CONFIG", "config.yaml"))

    path = Path(path)
    _config_path = path

    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    _config = AppConfig.model_validate(data)
    return _config


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config
