from __future__ import annotations

import json
import os

from google import genai
from google.genai import types

from ..config import get_config
from .base import ArticleInput, AuditResult, ClassifyResult

# NOTE: Gemini JSON mode (response_mime_type="application/json") requires the
# top-level response to be a JSON *object*, never a bare array.
# Classify wraps its array in {"articles": [...]} and unwraps on parse.

_CLASSIFY_SYSTEM = """You are an article classifier. Assign 1-5 tags with confidence scores.
Respond in the SAME language as the article.
Return JSON object only: {"articles": [{"article_id": N, "tags": [{"tag": "...", "confidence": 0.9}]}]}"""

_AUDIT_SYSTEM = """Summarize the article in 3-5 bullet points (article's language) and verify tags.
Return JSON object only: {"summary": "• ...", "verified_tags": [...], "classification_correct": true}"""


class GeminiProvider:
    def __init__(self) -> None:
        cfg = get_config()
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
        self._client = genai.Client(api_key=api_key)
        self._classify_model = cfg.provider.gemini_classify_model
        self._audit_model = cfg.provider.gemini_audit_model

    def classify(self, articles: list[ArticleInput]) -> list[ClassifyResult]:
        if not articles:
            return []

        user_msg = json.dumps([
            {"article_id": a.id, "title": a.title, "snippet": a.snippet}
            for a in articles
        ], ensure_ascii=False)

        resp = self._client.models.generate_content(
            model=self._classify_model,
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=_CLASSIFY_SYSTEM,
                response_mime_type="application/json",
                max_output_tokens=2048,
            ),
        )
        data = json.loads(resp.text)
        # Unwrap the object wrapper; fall back gracefully if model omits it
        if isinstance(data, dict):
            items = data.get("articles", list(data.values())[0] if data else [])
        else:
            items = data  # bare array fallback
        return [
            ClassifyResult(article_id=item["article_id"], tags=item.get("tags", []))
            for item in items
        ]

    def audit(self, article: ArticleInput) -> AuditResult:
        user_msg = json.dumps({
            "article_id": article.id,
            "title": article.title,
            "content": article.snippet,
        }, ensure_ascii=False)

        resp = self._client.models.generate_content(
            model=self._audit_model,
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=_AUDIT_SYSTEM,
                response_mime_type="application/json",
                max_output_tokens=1024,
            ),
        )
        data = json.loads(resp.text)
        return AuditResult(
            article_id=article.id,
            summary=data.get("summary", ""),
            verified_tags=data.get("verified_tags", []),
            classification_correct=data.get("classification_correct", True),
        )
