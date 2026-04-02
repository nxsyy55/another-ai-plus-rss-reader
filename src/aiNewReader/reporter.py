from __future__ import annotations

import json
import re
from typing import Any

from .config import get_config


def _estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ~= 4 chars or 0.75 words. 
    Using words * 1.33 as per the project's other stats.
    """
    words = len(re.findall(r"\S+", text))
    return int(words * 1.33)


def _dynamic_truncate(articles: list[dict[str, Any]], target_tokens: int) -> str:
    """Truncate articles to fit within target_tokens, prioritizing headers and equal sharing."""
    if not articles:
        return ""
    
    # Each article gets at least a small slice
    per_article_budget = max(200, target_tokens // len(articles))
    
    output_parts = []
    current_tokens = 0
    
    for art in articles:
        title = art.get("title", "Unknown Title")
        url = art.get("url", "")
        content = art.get("markdown_content", "")
        
        header = f"# [{title}]({url})\n"
        header_tokens = _estimate_tokens(header)
        
        # If we are already over budget, just add the header
        if current_tokens + header_tokens > target_tokens:
            break
            
        remaining_budget = target_tokens - current_tokens - header_tokens
        # Use the smaller of: its own length, the per_article_budget, or the remaining global budget
        article_content_budget = min(_estimate_tokens(content), per_article_budget, remaining_budget)
        
        # Simple word-based truncation for the budget
        words = content.split()
        # 1 word ~= 1.33 tokens => words = tokens / 1.33
        max_words = int(article_content_budget / 1.33)
        truncated_content = " ".join(words[:max_words])
        
        part = header + truncated_content
        output_parts.append(part)
        current_tokens += _estimate_tokens(part)
        
    return "\n\n---\n\n".join(output_parts)


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
    
    # Dynamic Truncation: Aim for 80% of context window to be safe (leaving room for prompt and output)
    target_tokens = int(provider.context_window * 0.8)
    combined_markdown = _dynamic_truncate(articles, target_tokens)

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
