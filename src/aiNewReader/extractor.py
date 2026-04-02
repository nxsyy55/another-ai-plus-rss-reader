from __future__ import annotations

import asyncio
import os
import re
import shutil
import tempfile
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
    # Count CJK characters
    cjk_count = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', text))
    # Count non-CJK words (splitting by whitespace)
    # First remove CJK characters to avoid double counting if they are surrounded by spaces
    non_cjk_text = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', ' ', text)
    word_count = len(re.findall(r"\S+", non_cjk_text))
    return cjk_count + word_count


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


async def _extract_with_defuddle(html: str) -> str | None:
    """Extract content using the defuddle CLI tool."""
    if not shutil.which("defuddle"):
        return None

    # Use a temporary file since defuddle parse requires a file path or URL
    fd, path = tempfile.mkstemp(suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(html)

        # Run defuddle parse --markdown
        process = await asyncio.create_subprocess_exec(
            "defuddle", "parse", path, "--markdown",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0 and stdout:
            # Clean up potential "Discarding URL" or other stderr-like noise from stdout if any
            content = stdout.decode("utf-8", errors="ignore").strip()
            # Some versions of defuddle might print debug info to stdout; 
            # ideally we just want the markdown. 
            if content:
                return content
        return None
    except Exception:
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _detect_language(text: str) -> str:
    """Simple heuristic for language detection (English vs Chinese)."""
    if not text:
        return "en"
    # Count CJK characters
    cjk_count = len(re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', text))
    # If more than 5% of characters are CJK, call it Chinese
    if cjk_count / len(text) > 0.05:
        return "zh"
    return "en"


async def extract_article(client: httpx.AsyncClient, article: dict[str, Any], firecrawl_enabled: bool = False) -> dict[str, Any]:
    url = article["url"]
    markdown: str | None = None
    full_content_extracted = False

    async with SEMAPHORE:
        # Stage B: try Trafilatura (Now primary engine)
        if not markdown:
            try:
                resp = await client.get(url, timeout=TIMEOUT)
                if resp.status_code < 400:
                    html = resp.text
                    markdown = _extract_with_trafilatura(html, url)
                    if markdown:
                        full_content_extracted = True
                    else:
                        # Stage C: fallback to Defuddle
                        markdown = await _extract_with_defuddle(html)
                        if markdown:
                            full_content_extracted = True
            except Exception:
                pass

        # Stage D: final fallback to RSS summary
        if not markdown:
            markdown = article.get("raw_summary", "")
            full_content_extracted = False

    word_count = _count_words(markdown or "")
    article["markdown_content"] = markdown or ""
    article["word_count"] = word_count
    article["language"] = _detect_language(markdown or "")
    article["media_only"] = _is_media_only(url, word_count)
    article["full_content_extracted"] = full_content_extracted
    return article


async def extract_all(articles: list[dict[str, Any]], firecrawl_enabled: bool = False) -> list[dict[str, Any]]:
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
            content = art.get("raw_summary", "")
            art["markdown_content"] = content
            art["word_count"] = _count_words(content)
            art["language"] = _detect_language(content)
            art["media_only"] = False
            output.append(art)
        else:
            output.append(result)
    return output
