from __future__ import annotations

from typing import Any

import lancedb

from ..embeddings import embed_text
from .store import LANCEDB_PATH, TABLE_NAME


async def search(
    query: str,
    limit: int = 10,
    language: str | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search over stored articles."""
    import json

    query_vec = await embed_text(query)

    try:
        db = lancedb.connect(str(LANCEDB_PATH))
        if TABLE_NAME not in db.table_names():
            return []
        table = db.open_table(TABLE_NAME)
    except Exception:
        return []

    q = table.search(query_vec).limit(limit * 3)  # over-fetch for post-filter

    try:
        results = q.to_list()
    except Exception:
        return []

    output: list[dict[str, Any]] = []
    for row in results:
        if language and row.get("language") != language:
            continue
        if tag:
            tags = json.loads(row.get("tags", "[]"))
            if tag.lower() not in [t.lower() for t in tags]:
                continue
        output.append({
            "id": row["id"],
            "url": row["url"],
            "title": row["title"],
            "language": row.get("language"),
            "tags": json.loads(row.get("tags", "[]")),
            "pub_date": row.get("pub_date"),
            "snippet": (row.get("markdown_content") or "")[:300],
            "_distance": row.get("_distance"),
        })
        if len(output) >= limit:
            break

    return output
