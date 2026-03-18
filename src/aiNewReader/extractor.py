from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx
import trafilatura

TIMEOUT = 15.0
SEMAPHORE = asyncio.Semaphore(10)


def _count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _extract_from_html(html: str, url: str) -> str | None:
    result = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        no_fallback=False,
        favor_precision=True,
    )
    return result


async def extract_article(client: httpx.AsyncClient, article: dict[str, Any]) -> dict[str, Any]:
    url = article["url"]
    async with SEMAPHORE:
        try:
            resp = await client.get(url, timeout=TIMEOUT)
            if resp.status_code >= 400:
                raise ValueError(f"HTTP {resp.status_code}")
            html = resp.text
        except Exception as exc:
            article["markdown_content"] = article.get("raw_summary", "")
            article["word_count"] = _count_words(article.get("raw_summary", ""))
            return article

    markdown = _extract_from_html(html, url)
    if not markdown:
        markdown = article.get("raw_summary", "")

    article["markdown_content"] = markdown
    article["word_count"] = _count_words(markdown)
    return article


async def extract_all(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "aiNewReader/0.1"},
        timeout=TIMEOUT,
    ) as client:
        tasks = [extract_article(client, art) for art in articles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    output: list[dict[str, Any]] = []
    for art, result in zip(articles, results):
        if isinstance(result, Exception):
            art["markdown_content"] = art.get("raw_summary", "")
            art["word_count"] = _count_words(art.get("raw_summary", ""))
            output.append(art)
        else:
            output.append(result)
    return output
