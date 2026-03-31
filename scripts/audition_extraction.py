#!/usr/bin/env python3
import asyncio
import os
import re
import shutil
import tempfile
from typing import Optional

import httpx
import trafilatura

# Target URLs for comparison
URLS = [
    "https://simonwillison.net/2026/Mar/30/mr-chatterbox/",
    "https://simonwillison.net/2026/Mar/29/pretext/",
    "https://www.theverge.com/2024/2/13/24071253/the-flipper-zero-has-a-powerful-new-hat-and-yes-it-runs-doom",
    "https://arstechnica.com/cars/2026/03/f1-in-japan-oh-no-what-have-they-done-to-all-the-fast-corners/",
    "https://github.blog/2026-03-24-secure-your-github-account-with-passkeys/" # Guessing this one might exist based on the pattern
]

OUTPUT_DIR = "output/audition"

def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))

def has_tables(text: str) -> bool:
    return "|" in text and "-|-" in text or (text.count("|") > 5 and "\n|" in text)

def has_blockquotes(text: str) -> bool:
    return "\n> " in text or text.startswith("> ")

def extract_trafilatura(html: str, url: str) -> str:
    result = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        no_fallback=False,
        favor_precision=True,
    )
    return result or ""

async def extract_defuddle(html: str) -> Optional[str]:
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
            content = stdout.decode("utf-8", errors="ignore").strip()
            return content
        return ""
    except Exception as e:
        print(f"Error running defuddle: {e}")
        return ""
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

async def audit_url(client: httpx.AsyncClient, url: str):
    print(f"Auditing: {url}...")
    try:
        resp = await client.get(url, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        print(f"  Failed to fetch {url}: {e}")
        return None

    # Trafilatura
    trafilatura_md = extract_trafilatura(html, url)
    
    # Defuddle
    defuddle_md = await extract_defuddle(html)

    # Save outputs
    safe_name = re.sub(r"[^a-z0-9]", "_", url.split("//")[-1])[:50]
    
    with open(f"{OUTPUT_DIR}/{safe_name}_trafilatura.md", "w", encoding="utf-8") as f:
        f.write(trafilatura_md)
    
    if defuddle_md is not None:
        with open(f"{OUTPUT_DIR}/{safe_name}_defuddle.md", "w", encoding="utf-8") as f:
            f.write(defuddle_md)

    return {
        "url": url,
        "trafilatura": {
            "success": bool(trafilatura_md),
            "words": count_words(trafilatura_md),
            "tables": has_tables(trafilatura_md),
            "quotes": has_blockquotes(trafilatura_md),
        },
        "defuddle": {
            "success": bool(defuddle_md) if defuddle_md is not None else "N/A",
            "words": count_words(defuddle_md) if defuddle_md is not None else 0,
            "tables": has_tables(defuddle_md) if defuddle_md is not None else False,
            "quotes": has_blockquotes(defuddle_md) if defuddle_md is not None else False,
            "available": defuddle_md is not None
        }
    }

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ExtractionAudit/1.0)"}
    async with httpx.AsyncClient(headers=headers) as client:
        tasks = [audit_url(client, url) for url in URLS]
        results = await asyncio.gather(*tasks)

    results = [r for r in results if r]
    
    # Print summary table
    print("\n" + "="*80)
    print(f"{'URL':<40} | {'Tool':<12} | {'Words':>6} | {'TBL':<3} | {'QUO':<3}")
    print("-" * 80)
    
    for r in results:
        url_trunc = (r['url'][:37] + '...') if len(r['url']) > 40 else r['url']
        
        # Trafilatura row
        t = r['trafilatura']
        print(f"{url_trunc:<40} | {'Trafilatura':<12} | {t['words']:>6} | {'Y' if t['tables'] else 'N':<3} | {'Y' if t['quotes'] else 'N':<3}")
        
        # Defuddle row
        d = r['defuddle']
        if d['available']:
            print(f"{'':<40} | {'Defuddle':<12} | {d['words']:>6} | {'Y' if d['tables'] else 'N':<3} | {'Y' if d['quotes'] else 'N':<3}")
        else:
            print(f"{'':<40} | {'Defuddle':<12} | {'N/A':>6} | {'N/A':<3} | {'N/A':<3}")
        print("-" * 80)

if __name__ == "__main__":
    asyncio.run(main())
