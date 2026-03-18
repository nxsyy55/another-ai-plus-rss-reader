from __future__ import annotations

from typing import Any

from .db import get_db, set_article_tags
from .providers import ArticleInput, get_provider

BATCH_SIZE = 10


def _make_snippet(article: dict[str, Any]) -> str:
    content = article.get("markdown_content") or article.get("raw_summary") or ""
    return content[:300]


def classify_articles(
    articles: list[dict[str, Any]],
    provider_name: str | None = None,
) -> list[dict[str, Any]]:
    """Classify articles in batches. Updates each article dict with 'tags' key."""
    if not articles:
        return articles

    provider = get_provider(provider_name)

    # Build ArticleInput list
    inputs = [
        ArticleInput(
            id=art["id"],
            url=art["url"],
            title=art.get("title", ""),
            language=art.get("language"),
            snippet=_make_snippet(art),
        )
        for art in articles
    ]

    id_to_art = {art["id"]: art for art in articles}

    # Process in batches
    for i in range(0, len(inputs), BATCH_SIZE):
        batch = inputs[i : i + BATCH_SIZE]
        try:
            results = provider.classify(batch)
        except Exception as exc:
            print(f"  [WARN] classify batch failed: {exc}")
            for inp in batch:
                id_to_art[inp.id]["tags"] = []
            continue

        for result in results:
            art = id_to_art.get(result.article_id)
            if art is None:
                continue
            art["tags"] = result.tags
            with get_db() as conn:
                set_article_tags(conn, art["id"], result.tags)

    # Ensure all articles have a tags key
    for art in articles:
        art.setdefault("tags", [])

    return articles
