from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ArticleInput:
    id: int
    url: str
    title: str
    language: str | None
    snippet: str  # first 300 chars of markdown_content or raw_summary


@dataclass
class ClassifyResult:
    article_id: int
    tags: list[dict]  # [{"tag": str, "confidence": float}]


@dataclass
class AuditResult:
    article_id: int
    summary: str  # 3-5 bullet points in article's language
    verified_tags: list[dict]  # [{"tag": str, "confidence": float}]
    classification_correct: bool


@runtime_checkable
class Provider(Protocol):
    @property
    def context_window(self) -> int: ...
    def classify(self, articles: list[ArticleInput]) -> list[ClassifyResult]: ...
    def audit(self, article: ArticleInput) -> AuditResult: ...
    def complete(self, system: str, user: str, max_tokens: int = 2048) -> str: ...
