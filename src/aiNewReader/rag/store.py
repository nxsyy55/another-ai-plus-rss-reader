from __future__ import annotations

from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from ..embeddings import embed_text, unpack_embedding

LANCEDB_PATH = Path("data/lancedb")
TABLE_NAME = "articles"

_SCHEMA = pa.schema([
    pa.field("id", pa.int64()),
    pa.field("url", pa.utf8()),
    pa.field("title", pa.utf8()),
    pa.field("language", pa.utf8()),
    pa.field("tags", pa.utf8()),  # JSON array string
    pa.field("pub_date", pa.utf8()),
    pa.field("markdown_content", pa.utf8()),
    pa.field("vector", pa.list_(pa.float32(), 1024)),
])


def _get_table() -> lancedb.table.Table:
    LANCEDB_PATH.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(LANCEDB_PATH))
    if TABLE_NAME not in db.table_names():
        return db.create_table(TABLE_NAME, schema=_SCHEMA)
    return db.open_table(TABLE_NAME)


def index_article(article: dict[str, Any], embedding: list[float] | None = None) -> None:
    """Index a single article into LanceDB. Reuses stored embedding if available."""
    import json

    if embedding is None and article.get("embedding"):
        embedding = unpack_embedding(article["embedding"])

    if embedding is None:
        return  # Can't index without a vector

    table = _get_table()
    record = {
        "id": article["id"],
        "url": article.get("url", ""),
        "title": article.get("title", ""),
        "language": article.get("language") or "",
        "tags": json.dumps([t["tag"] for t in article.get("tags", [])]),
        "pub_date": article.get("pub_date") or "",
        "markdown_content": (article.get("markdown_content") or "")[:10000],
        "vector": embedding,
    }
    # Remove existing entry for this URL
    try:
        table.delete(f"url = '{article['url'].replace(chr(39), chr(39)*2)}'")
    except Exception:
        pass
    table.add([record])


def index_articles_batch(articles: list[dict[str, Any]]) -> int:
    """Index multiple articles. Returns count indexed."""
    indexed = 0
    for art in articles:
        try:
            emb = unpack_embedding(art["embedding"]) if art.get("embedding") else None
            index_article(art, emb)
            indexed += 1
        except Exception as exc:
            print(f"  [WARN] RAG index failed for {art.get('url')}: {exc}")
    return indexed
