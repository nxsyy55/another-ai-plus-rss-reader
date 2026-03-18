from __future__ import annotations

import httpx

from .config import get_config
from .db import get_db, get_all_feeds, mark_feed_health


async def check_feed_health(feed_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.head(feed_url)
            return resp.status_code < 400
    except Exception:
        return False


async def check_ollama() -> bool:
    cfg = get_config()
    base_url = cfg.provider.ollama_base_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code != 200:
                return False
            models = {m["name"].split(":")[0] for m in resp.json().get("models", [])}
            embed_model = cfg.provider.ollama_embed_model.split(":")[0]
            return embed_model in models
    except Exception:
        return False


async def run_health_check(verbose: bool = False) -> dict[str, int]:
    import asyncio

    results = {"healthy": 0, "unhealthy": 0}

    with get_db() as conn:
        feeds = get_all_feeds(conn)

    async def _check(feed_row: object) -> None:
        healthy = await check_feed_health(feed_row["url"])
        with get_db() as conn:
            mark_feed_health(conn, feed_row["id"], healthy)
        if healthy:
            results["healthy"] += 1
        else:
            results["unhealthy"] += 1
        if verbose:
            status = "OK" if healthy else "DEAD"
            print(f"  [{status}] {feed_row['name'] or feed_row['url']}")

    await asyncio.gather(*[_check(f) for f in feeds if f["enabled"]])
    return results
