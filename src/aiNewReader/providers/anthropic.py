from __future__ import annotations

import json

import anthropic as _anthropic

from ..config import get_config
from .base import ArticleInput, AuditResult, ClassifyResult

_CLASSIFY_SYSTEM = """You are an article classifier. Given article titles and snippets, assign 1-5 relevant tags and confidence scores.
Respond in the SAME language as the article. Do NOT translate tags.
Return JSON array: [{"article_id": N, "tags": [{"tag": "...", "confidence": 0.9}, ...]}]
Use only relevant, specific tags. Be concise."""

_AUDIT_SYSTEM = """You are an article auditor. Summarize the article in 3-5 bullet points (in the article's original language) and verify/correct its classification tags.
Return JSON: {"summary": "• point1\n• point2\n...", "verified_tags": [{"tag": "...", "confidence": 0.9}], "classification_correct": true}"""


class AnthropicProvider:
    def __init__(self) -> None:
        cfg = get_config()
        self._client = _anthropic.Anthropic()
        self._model = cfg.provider.anthropic_model

    @property
    def context_window(self) -> int:
        return 200_000

    def classify(self, articles: list[ArticleInput]) -> list[ClassifyResult]:
        if not articles:
            return []

        user_msg = json.dumps([
            {"article_id": a.id, "title": a.title, "snippet": a.snippet}
            for a in articles
        ], ensure_ascii=False)

        resp = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        results: list[ClassifyResult] = []
        for item in data:
            results.append(ClassifyResult(
                article_id=item["article_id"],
                tags=item.get("tags", []),
            ))
        return results

    def audit(self, article: ArticleInput) -> AuditResult:
        user_msg = json.dumps({
            "article_id": article.id,
            "title": article.title,
            "content": article.snippet,
        }, ensure_ascii=False)

        resp = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_AUDIT_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)

        return AuditResult(
            article_id=article.id,
            summary=data.get("summary", ""),
            verified_tags=data.get("verified_tags", []),
            classification_correct=data.get("classification_correct", True),
        )

    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
