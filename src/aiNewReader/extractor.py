from __future__ import annotations

import asyncio
import os
import re
from typing import Any

import httpx
import trafilatura

TIMEOUT = 15.0
SEMAPHORE = asyncio.Semaphore(10)

# Video/audio URL patterns — articles whose URL matches AND have little text
# are considered media-only and dropped from the pipeline
_MEDIA_URL_PATTERNS = re.compile(
    r"(youtube\.com/watch|youtu\.be/|vimeo\.com/|twitch\.tv/|"
    r"spotify\.com/episode|soundcloud\.com/|podcasts?\.|"
    r"anchor\.fm/|buzzsprout\.com/|podbean\.com/)",
    re.IGNORECASE,
)
_MEDIA_WORD_THRESHOLD = 40  # articles below this word count + media URL = filtered


def _count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _is_media_only(url: str, word_count: int) -> bool:
    """True if article is a video/audio page with no readable text body."""
    return bool(_MEDIA_URL_PATTERNS.search(url)) and word_count < _MEDIA_WORD_THRESHOLD


def _extract_with_trafilatura(html: str, url: str) -> str | None:
    return trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        no_fallback=False,
        favor_precision=True,
    )


def _firecrawl_scrape(url: str) -> str | None:
    """Synchronous Firecrawl scrape — run via asyncio.to_thread()."""
    try:
        from firecrawl import FirecrawlApp
        api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        if not api_key:
            return None
        app = FirecrawlApp(api_key=api_key)
        result = app.scrape_url(url, formats=["markdown"], only_main_content=True)
        return result.markdown or None
    except Exception:
        return None


async def extract_article(client: httpx.AsyncClient, article: dict[str, Any], firecrawl_enabled: bool) -> dict[str, Any]:
    url = article["url"]
    markdown: str | None = None

    async with SEMAPHORE:
        # Stage A: try Firecrawl (handles paywalls, JS rendering)
        if firecrawl_enabled:
            markdown = await asyncio.to_thread(_firecrawl_scrape, url)

        # Stage B: fallback to trafilatura
        if not markdown:
            try:
                resp = await client.get(url, timeout=TIMEOUT)
                if resp.status_code < 400:
                    markdown = _extract_with_trafilatura(resp.text, url)
            except Exception:
                pass

        # Stage C: fallback to RSS summary
        if not markdown:
            markdown = article.get("raw_summary", "")

    word_count = _count_words(markdown)
    article["markdown_content"] = markdown
    article["word_count"] = word_count
    article["media_only"] = _is_media_only(url, word_count)
    return article


async def extract_all(articles: list[dict[str, Any]], firecrawl_enabled: bool = True) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "aiNewReader/0.1"},
        timeout=TIMEOUT,
    ) as client:
        tasks = [extract_article(client, art, firecrawl_enabled) for art in articles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    output: list[dict[str, Any]] = []
    for art, result in zip(articles, results):
        if isinstance(result, Exception):
            art["markdown_content"] = art.get("raw_summary", "")
            art["word_count"] = _count_words(art.get("raw_summary", ""))
            art["media_only"] = False
            output.append(art)
        else:
            output.append(result)
    return output
