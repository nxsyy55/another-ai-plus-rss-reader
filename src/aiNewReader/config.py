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
    classify_model: str = "claude-haiku-4-5-20251001"
    audit_model: str = "claude-sonnet-4-6"
    gemini_classify_model: str = "gemini-3-flash-preview"
    gemini_audit_model: str = "gemini-3.1-pro-preview"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "bge-m3"
    ollama_chat_model: str = "qwen3.5:9b"
    deepseek_classify_model: str = "deepseek-chat"
    deepseek_audit_model: str = "deepseek-chat"


class DashboardConfig(BaseModel):
    port: int = 8080
    host: str = "localhost"


class AppConfig(BaseModel):
    hours_window: int = 24
    audit_word_threshold: int = 500
    max_articles_per_run: int = 300
    health_check_interval_hours: int = 24
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)


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
