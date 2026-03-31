from __future__ import annotations

import re
from typing import Any
from .db import get_db

PAYWALL_KEYWORDS = [
    r"login",
    r"subscribe",
    r"account",
    r"members? only",
    r"paywall",
    r"premium",
    r"sign up",
    r"create an account",
    r"continued reading",
    r"read the full story",
]

WORD_COUNT_THRESHOLD = 50

def is_likely_paywall(article: dict[str, Any]) -> bool:
    # Handle the case where word_count is explicitly None in the database
    word_count = article.get("word_count")
    if word_count is None:
        word_count = 0
        
    # If word_count is low and it's not a media-only URL (handled in extractor)
    if word_count < WORD_COUNT_THRESHOLD:
        # Check markdown content for paywall keywords
        content = (article.get("markdown_content") or "").lower()
        title = (article.get("title") or "").lower()
        
        for pattern in PAYWALL_KEYWORDS:
            if re.search(pattern, content) or re.search(pattern, title):
                return True
        
        # If it's very short and not media, it's suspicious even without keywords
        if word_count < 30 and not article.get("media_only", False):
            return True
            
    return False

def clean_paywalls(dry_run: bool = True) -> dict[str, Any]:
    stats = {
        "checked": 0,
        "identified": 0,
        "deleted": 0,
        "polluted_feeds": {} # feed_id -> count
    }
    
    with get_db() as conn:
        # Fetch articles that aren't already excluded and have extraction status
        articles = conn.execute("""
            SELECT a.id, a.url, a.title, a.word_count, a.markdown_content, a.feed_id, f.name as feed_name
            FROM articles a
            JOIN feeds f ON a.feed_id = f.id
            WHERE a.excluded_post_audit = 0
        """).fetchall()
        
        to_delete = []
        for art in articles:
            stats["checked"] += 1
            if is_likely_paywall(dict(art)):
                stats["identified"] += 1
                to_delete.append(art["id"])
                
                feed_key = f"{art['feed_name']} ({art['feed_id']})"
                stats["polluted_feeds"][feed_key] = stats["polluted_feeds"].get(feed_key, 0) + 1
        
        if not dry_run and to_delete:
            placeholders = ", ".join("?" for _ in to_delete)
            # We don't actually want to delete the article record usually, 
            # maybe just mark it as excluded so it doesn't show up in reports/digests
            conn.execute(f"UPDATE articles SET excluded_post_audit = 1 WHERE id IN ({placeholders})", to_delete)
            stats["deleted"] = len(to_delete)
            
    return stats
