from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import fastfeedparser
import httpx

from .config import get_config
from .db import get_db, get_all_feeds, update_feed_cache, upsert_feed

SEMAPHORE = asyncio.Semaphore(20)
TIMEOUT = 10.0


def _normalize_date(dt: Any) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _content_hash(title: str, summary: str) -> str:
    raw = f"{title}|{summary}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def _fetch_feed(
    client: httpx.AsyncClient,
    feed_row: Any,
    since: datetime,
) -> list[dict[str, Any]]:
    url = feed_row["url"]
    feed_id = feed_row["id"]
    headers: dict[str, str] = {}
    if feed_row["etag"]:
        headers["If-None-Match"] = feed_row["etag"]
    if feed_row["last_modified"]:
        headers["If-Modified-Since"] = feed_row["last_modified"]

    async with SEMAPHORE:
        try:
            resp = await client.get(url, headers=headers, timeout=TIMEOUT)
        except Exception as exc:
            print(f"  [WARN] fetch failed {url}: {exc}")
            return []

    if resp.status_code == 304:
        return []
    if resp.status_code >= 400:
        print(f"  [WARN] HTTP {resp.status_code} for {url}")
        return []

    etag = resp.headers.get("etag")
    last_modified = resp.headers.get("last-modified")

    with get_db() as conn:
        update_feed_cache(conn, feed_id, etag, last_modified)

    try:
        feed = fastfeedparser.parse(resp.text)
    except Exception as exc:
        print(f"  [WARN] parse failed {url}: {exc}")
        return []

    articles: list[dict[str, Any]] = []
    for entry in feed.entries:
        pub = _normalize_date(getattr(entry, "published", None) or getattr(entry, "updated", None))
        if pub and pub < since:
            continue

        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", "") or ""
        summary = getattr(entry, "summary", "") or ""

        if not link:
            continue

        articles.append({
            "url": link,
            "title": title,
            "pub_date": pub.isoformat() if pub else datetime.utcnow().isoformat(),
            "feed_id": feed_id,
            "raw_summary": summary[:2000],
            "content_hash": _content_hash(title, summary),
            "dedup_status": "original",
        })

    return articles


async def fetch_all_feeds(hours: int) -> list[dict[str, Any]]:
    cfg = get_config()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    with get_db() as conn:
        feeds = [f for f in get_all_feeds(conn) if f["enabled"] and f["healthy"]]

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "aiNewReader/0.1 (+https://github.com/local/ainewreader)"},
    ) as client:
        tasks = [_fetch_feed(client, feed, since) for feed in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    articles: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, list):
            articles.extend(result)

    # Deduplicate by URL before returning
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    max_articles = cfg.max_articles_per_run
    return unique[:max_articles]


def sync_feeds_from_yaml(feeds_yaml: list[dict[str, Any]]) -> None:
    with get_db() as conn:
        for feed in feeds_yaml:
            upsert_feed(conn, feed["url"], feed.get("name", feed["url"]), feed.get("enabled", True))


def save_feeds_to_yaml(path: "Path | str" = "feeds.yaml") -> None:
    """Write current DB feeds back to feeds.yaml."""
    from pathlib import Path as _Path
    import yaml
    with get_db() as conn:
        rows = get_all_feeds(conn)
    data = {"feeds": [{"url": r["url"], "name": r["name"] or r["url"], "enabled": bool(r["enabled"])} for r in rows]}
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def parse_opml(content: str) -> list[dict[str, Any]]:
    """Parse OPML XML and return list of {url, name} dicts."""
    import xml.etree.ElementTree as ET
    feeds: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise ValueError(f"Invalid OPML: {e}") from e

    for outline in root.iter("outline"):
        url = outline.get("xmlUrl") or outline.get("url")
        if not url:
            continue
        name = outline.get("title") or outline.get("text") or url
        feeds.append({"url": url, "name": name, "enabled": True})

    return feeds


def import_opml(path: "Path | str") -> list[dict[str, Any]]:
    """Parse an OPML file and upsert all feeds into the DB + feeds.yaml."""
    from pathlib import Path as _Path
    content = _Path(path).read_text(encoding="utf-8", errors="replace")
    feeds = parse_opml(content)
    with get_db() as conn:
        for feed in feeds:
            upsert_feed(conn, feed["url"], feed["name"], True)
    save_feeds_to_yaml()
    return feeds
