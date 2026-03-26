from __future__ import annotations

import json
from typing import Any

_REPORT_SYSTEM = """You are a senior news analyst writing a concise daily briefing.
Given a list of today's filtered articles (with titles, URLs, tags, and summaries),
produce a structured JSON report with these fields:
- "executive_summary": 2-3 paragraphs of flowing prose covering the major themes
- "key_themes": list of up to 5 objects, each with:
    - "theme": short label (3-6 words)
    - "insight": 1-2 sentence analysis
    - "articles": list of {title, url} for the 2-4 most relevant articles
- "notable_picks": list of up to 5 {title, url, reason} — standout articles worth reading

Write in the same language as the majority of articles. Be analytical, not just descriptive.
Return ONLY the JSON object, no markdown fences."""


def _build_user_message(articles: list[dict[str, Any]]) -> str:
    items = []
    for art in articles:
        tags = [t["tag"] for t in art.get("tags", [])]
        summary = art.get("audit_summary") or art.get("raw_summary", "")[:300]
        items.append({
            "title": art.get("title", ""),
            "url": art.get("url", ""),
            "tags": tags,
            "summary": summary,
        })
    return json.dumps(items, ensure_ascii=False)


def generate_report(
    articles: list[dict[str, Any]],
    provider_name: str | None,
) -> dict[str, Any]:
    """Call LLM to generate a structured daily report. Returns parsed JSON dict."""
    from .providers import get_provider

    if not articles:
        return {
            "executive_summary": "No articles were collected in this run.",
            "key_themes": [],
            "notable_picks": [],
        }

    provider = get_provider(provider_name)
    user_msg = _build_user_message(articles)

    try:
        raw = provider.complete(_REPORT_SYSTEM, user_msg, max_tokens=2048)
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as exc:
        # Graceful degradation: return minimal report rather than crashing pipeline
        print(f"  [WARN] Report generation failed: {exc}")
        return {
            "executive_summary": f"Report generation failed: {exc}",
            "key_themes": [],
            "notable_picks": [],
        }
