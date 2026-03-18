from __future__ import annotations

from typing import Any

from .db import get_db, set_article_tags, update_article_audit
from .providers import ArticleInput, get_provider

MAX_CONTENT_LEN = 8000  # chars sent to audit LLM


def _make_article_input(article: dict[str, Any]) -> ArticleInput:
    content = article.get("markdown_content") or article.get("raw_summary") or ""
    return ArticleInput(
        id=article["id"],
        url=article["url"],
        title=article.get("title", ""),
        language=article.get("language"),
        snippet=content[:MAX_CONTENT_LEN],
    )


def audit_articles(
    articles: list[dict[str, Any]],
    word_threshold: int,
    provider_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    Audit articles whose word_count exceeds word_threshold.
    Mutates each article dict with audit results.
    Returns the full list (including un-audited articles).
    """
    if not articles:
        return articles

    provider = get_provider(provider_name)
    to_audit = [a for a in articles if (a.get("word_count") or 0) > word_threshold]

    for art in to_audit:
        inp = _make_article_input(art)
        try:
            result = provider.audit(inp)
        except Exception as exc:
            print(f"  [WARN] audit failed for {art['url']}: {exc}")
            continue

        art["audit_summary"] = result.summary
        art["audit_classification_correct"] = result.classification_correct

        # Update tags if classification was wrong
        if not result.classification_correct and result.verified_tags:
            art["tags"] = result.verified_tags
            with get_db() as conn:
                set_article_tags(conn, art["id"], result.verified_tags)

        with get_db() as conn:
            update_article_audit(
                conn,
                art["id"],
                result.summary,
                result.classification_correct,
            )

    return articles
