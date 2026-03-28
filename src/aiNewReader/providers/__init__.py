from __future__ import annotations

from .base import ArticleInput, AuditResult, ClassifyResult, Provider


def get_provider(name: str | None = None) -> Provider:
    from ..config import get_config
    cfg = get_config()
    name = name or cfg.provider.default

    if name == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider()
    elif name == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider()
    else:
        from .ollama import OllamaProvider
        return OllamaProvider()


__all__ = ["ArticleInput", "AuditResult", "ClassifyResult", "Provider", "get_provider"]
