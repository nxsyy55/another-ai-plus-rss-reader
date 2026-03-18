from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from rapidfuzz import fuzz

from .db import get_db, get_recent_articles, update_article_dedup
from .embeddings import cosine_similarity, embed_texts, pack_embedding, unpack_embedding

# Tracking params to strip from URLs
_STRIP_PARAMS = frozenset([
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "referrer", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
])
_FUZZY_THRESHOLD = 80
_SEMANTIC_THRESHOLD = 0.92


def normalize_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query, keep_blank_values=False)
        qs = {k: v for k, v in qs.items() if k.lower() not in _STRIP_PARAMS}
        query = urlencode(sorted(qs.items()), doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url


def _normalize_title(title: str) -> str:
    t = unicodedata.normalize("NFKC", title.lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t


async def deduplicate(
    articles: list[dict[str, Any]],
    hours_window: int = 24,
) -> list[dict[str, Any]]:
    """
    3-layer dedup. Returns articles with dedup_status set.
    Articles marked as duplicates keep their dedup_status set but are removed from output.
    """
    # Layer 1: URL normalization
    seen_urls: dict[str, int] = {}  # normalized_url -> index in `articles`
    for i, art in enumerate(articles):
        norm = normalize_url(art["url"])
        if norm in seen_urls:
            art["dedup_status"] = "duplicate_url"
        else:
            seen_urls[norm] = i

    originals = [a for a in articles if a.get("dedup_status") == "original"]

    # Layer 2: Fuzzy title
    seen_titles: list[str] = []
    for art in originals:
        norm_title = _normalize_title(art.get("title", ""))
        for existing in seen_titles:
            score = fuzz.token_sort_ratio(norm_title, existing)
            if score >= _FUZZY_THRESHOLD:
                art["dedup_status"] = "duplicate_fuzzy"
                break
        if art.get("dedup_status") == "original":
            seen_titles.append(norm_title)

    originals = [a for a in originals if a.get("dedup_status") == "original"]

    # Layer 3: Semantic similarity via bge-m3
    # Compare against DB articles from the same window AND within current batch
    with get_db() as conn:
        db_articles = get_recent_articles(conn, hours_window)

    db_embeddings: list[list[float]] = []
    for row in db_articles:
        if row["embedding"]:
            db_embeddings.append(unpack_embedding(row["embedding"]))

    # Embed new articles
    texts = [f"{a.get('title', '')} {a.get('raw_summary', '')}"[:512] for a in originals]
    if texts:
        vecs = await embed_texts(texts)
        batch_embeddings: list[list[float]] = []
        for i, (art, vec) in enumerate(zip(originals, vecs)):
            art["_embedding"] = vec
            art["embedding"] = pack_embedding(vec)

            # Check against DB embeddings
            is_dup = False
            for db_vec in db_embeddings:
                if cosine_similarity(vec, db_vec) >= _SEMANTIC_THRESHOLD:
                    art["dedup_status"] = "duplicate_semantic"
                    is_dup = True
                    break

            # Check against already-accepted articles in this batch
            if not is_dup:
                for prev_vec in batch_embeddings:
                    if cosine_similarity(vec, prev_vec) >= _SEMANTIC_THRESHOLD:
                        art["dedup_status"] = "duplicate_semantic"
                        is_dup = True
                        break

            if not is_dup:
                batch_embeddings.append(vec)

    return articles
