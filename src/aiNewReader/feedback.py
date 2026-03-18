from __future__ import annotations

from typing import Any

from .db import get_db, get_article_by_url, add_feedback, get_feedback_embeddings, has_dislike_signal
from .embeddings import cosine_similarity, embed_text, pack_embedding, unpack_embedding


async def record_feedback(url: str, signal: int) -> bool:
    """Record a like (+1) or dislike (-1) for an article by URL."""
    with get_db() as conn:
        row = get_article_by_url(conn, url)
        if row is None:
            return False
        article_id = row["id"]

    # Reuse stored embedding if available
    embedding_blob: bytes | None = None
    if row["embedding"]:
        embedding_blob = row["embedding"]
    else:
        text = f"{row['title'] or ''} {row['raw_summary'] or ''}"[:512]
        vec = await embed_text(text)
        embedding_blob = pack_embedding(vec)

    with get_db() as conn:
        add_feedback(conn, article_id, signal, embedding_blob)

    return True


async def compute_preference_scores(article_ids: list[int]) -> dict[int, float]:
    """
    Compute preference score for each article_id.
    Score = cosine(article, liked_centroid) - cosine(article, disliked_centroid)
    Returns dict mapping article_id -> score in [-1.0, 1.0].
    """
    with get_db() as conn:
        fb_rows = get_feedback_embeddings(conn)

    if not fb_rows:
        return {aid: 0.0 for aid in article_ids}

    liked_vecs: list[list[float]] = []
    disliked_vecs: list[list[float]] = []

    for row in fb_rows:
        if not row["embedding"]:
            continue
        vec = unpack_embedding(row["embedding"])
        if row["signal"] == 1:
            liked_vecs.append(vec)
        elif row["signal"] == -1:
            disliked_vecs.append(vec)

    def centroid(vecs: list[list[float]]) -> list[float] | None:
        if not vecs:
            return None
        n = len(vecs)
        dims = len(vecs[0])
        result = [0.0] * dims
        for vec in vecs:
            for i, v in enumerate(vec):
                result[i] += v / n
        return result

    liked_centroid = centroid(liked_vecs)
    disliked_centroid = centroid(disliked_vecs)

    scores: dict[int, float] = {}
    with get_db() as conn:
        for aid in article_ids:
            row = conn.execute("SELECT embedding FROM articles WHERE id=?", (aid,)).fetchone()
            if row is None or not row["embedding"]:
                scores[aid] = 0.0
                continue
            vec = unpack_embedding(row["embedding"])
            liked_sim = cosine_similarity(vec, liked_centroid) if liked_centroid else 0.0
            disliked_sim = cosine_similarity(vec, disliked_centroid) if disliked_centroid else 0.0
            scores[aid] = liked_sim - disliked_sim

    return scores
