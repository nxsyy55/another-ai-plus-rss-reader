from __future__ import annotations

import json
from typing import Any

from .config import get_config


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
        raw = provider.complete(get_config().report_prompt, combined_markdown, max_tokens=8192)
        
        # Robustly extract JSON block
        clean = raw.strip()
        start = clean.find("{")
        end = clean.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(clean[start:end + 1])
            except json.JSONDecodeError:
                pass
            
        # Fallback: if not valid JSON, treat the whole response as the executive summary
        return {
            "executive_summary": raw,
            "key_themes": [],
            "notable_picks": [],
        }
    except Exception as exc:
        # Graceful degradation: return minimal report rather than crashing pipeline
        print(f"  [WARN] Report generation failed: {exc}")
        return {
            "executive_summary": f"Report generation failed: {exc}",
            "key_themes": [],
            "notable_picks": [],
        }

