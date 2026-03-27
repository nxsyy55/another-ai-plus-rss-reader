from __future__ import annotations

import json
from typing import Any

_REPORT_SYSTEM = """You are a senior news analyst writing a concise daily briefing.
Given the scraped markdown text of today's articles,
produce a structured JSON report with these fields:
- "executive_summary": 2-3 paragraphs of flowing prose covering the major themes
- "key_themes": list of up to 5 objects, each with:
    - "theme": short label (3-6 words)
    - "insight": 1-2 sentence analysis
    - "articles": list of {title, url} for the 2-4 most relevant articles
- "notable_picks": list of up to 5 {title, url, reason} — standout articles worth reading

Write in the same language as the majority of articles. Be analytical, not just descriptive.
Return ONLY the JSON object, no markdown fences."""


def generate_report(
    combined_markdown: str,
    provider_name: str | None,
) -> dict[str, Any]:
    """Call LLM to generate a structured daily report. Returns parsed JSON dict."""
    from .providers import get_provider

    if not combined_markdown.strip():
        return {
            "executive_summary": "No articles were collected in this run.",
            "key_themes": [],
            "notable_picks": [],
        }

    provider = get_provider(provider_name)

    try:
        raw = provider.complete(_REPORT_SYSTEM, combined_markdown, max_tokens=8192)
        
        # Robustly extract JSON block
        raw = raw.strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end + 1]
            
        return json.loads(raw)
    except Exception as exc:
        # Graceful degradation: return minimal report rather than crashing pipeline
        print(f"  [WARN] Report generation failed: {exc}")
        return {
            "executive_summary": f"Report generation failed: {exc}",
            "key_themes": [],
            "notable_picks": [],
        }

