from __future__ import annotations

import json

from openai import OpenAI

from ..config import get_config
from .base import ArticleInput, AuditResult, ClassifyResult

_CLASSIFY_SYSTEM = """Classify articles with 1-5 tags. Respond in article's language.
Return JSON array only: [{"article_id": N, "tags": [{"tag": "...", "confidence": 0.9}]}]"""

_AUDIT_SYSTEM = """Summarize article in 3-5 bullet points (article's language) and verify tags.
Return JSON only: {"summary": "• ...", "verified_tags": [...], "classification_correct": true}"""

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider:
    def __init__(self) -> None:
        import os
        self._client = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=DEEPSEEK_BASE_URL,
        )

    def _chat(self, system: str, user: str, model: str = "deepseek-chat") -> str:
        resp = self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""

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
            data = list(data.values())[0] if data else []
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
