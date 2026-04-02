from __future__ import annotations

import json

import httpx

from ..config import get_config
from .base import ArticleInput, AuditResult, ClassifyResult

_CLASSIFY_SYSTEM = """Classify articles with 1-5 tags. Respond in article's language.
Return JSON array only: [{"article_id": N, "tags": [{"tag": "...", "confidence": 0.9}]}]"""

_AUDIT_SYSTEM = """Summarize article in 3-5 bullet points (article's language) and verify tags.
Return JSON only: {"summary": "• ...", "verified_tags": [...], "classification_correct": true}"""


class OllamaProvider:
    def __init__(self) -> None:
        cfg = get_config()
        self._base_url = cfg.provider.ollama_base_url
        self._model = cfg.provider.ollama_chat_model

    @property
    def context_window(self) -> int:
        return 32_000

    def _chat(self, system: str, user: str, model: str | None = None) -> str:
        model = model or self._model
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    def classify(self, articles: list[ArticleInput]) -> list[ClassifyResult]:
        if not articles:
            return []
        user_msg = json.dumps([
            {"article_id": a.id, "title": a.title, "snippet": a.snippet}
            for a in articles
        ], ensure_ascii=False)
        raw = self._chat(_CLASSIFY_SYSTEM, user_msg)
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("articles", list(data.values())[0] if data else [])
        return [
            ClassifyResult(article_id=item["article_id"], tags=item.get("tags", []))
            for item in data
        ]

    def audit(self, article: ArticleInput) -> AuditResult:
        user_msg = json.dumps({
            "article_id": article.id,
            "title": article.title,
            "content": article.snippet,
        }, ensure_ascii=False)
        raw = self._chat(_AUDIT_SYSTEM, user_msg)
        data = json.loads(raw)
        return AuditResult(
            article_id=article.id,
            summary=data.get("summary", ""),
            verified_tags=data.get("verified_tags", []),
            classification_correct=data.get("classification_correct", True),
        )

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
