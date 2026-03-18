from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .db import get_db, get_all_filter_rules, upsert_filter_rule, delete_filter_rule

FILTERS_PATH = Path("filters.yaml")


def sync_rules_from_yaml(path: Path = FILTERS_PATH) -> None:
    """Load filters.yaml and sync to DB. Called on every startup."""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    rules = data.get("rules", [])
    with get_db() as conn:
        for rule in rules:
            upsert_filter_rule(conn, rule)


def save_rules_to_yaml(rules: list[dict[str, Any]], path: Path = FILTERS_PATH) -> None:
    """Write rules back to filters.yaml (called by dashboard edits)."""
    data = {"rules": rules}
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_rules() -> list[dict[str, Any]]:
    """Return all enabled filter rules from DB, sorted by priority desc."""
    with get_db() as conn:
        rows = get_all_filter_rules(conn)
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "action": r["action"],
            "tags": json.loads(r["tags"]),
            "keywords": json.loads(r["keywords"]),
            "priority": r["priority"],
            "enabled": bool(r["enabled"]),
        }
        for r in rows
        if r["enabled"]
    ]


def _matches_rule(article: dict[str, Any], rule: dict[str, Any]) -> bool:
    article_tags = {t["tag"].lower() for t in article.get("tags", [])}
    rule_tags = {t.lower() for t in rule.get("tags", [])}
    if article_tags & rule_tags:
        return True

    title_lower = (article.get("title") or "").lower()
    for kw in rule.get("keywords", []):
        if kw.lower() in title_lower:
            return True

    return False


def filter_articles(
    articles: list[dict[str, Any]],
    preference_scores: dict[int, float] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate rules in priority order (highest first).
    Returns articles that pass the filter.
    """
    rules = load_rules()
    if not rules:
        return articles

    include_rules = [r for r in rules if r["action"] == "include"]
    exclude_rules = [r for r in rules if r["action"] == "exclude"]
    preference_scores = preference_scores or {}

    accepted: list[dict[str, Any]] = []

    for art in articles:
        art_id = art["id"]
        pref_score = preference_scores.get(art_id, 0.0)

        # Check for explicit dislike signal override
        with get_db() as conn:
            from .db import has_dislike_signal
            explicit_dislike = has_dislike_signal(conn, art_id)

        # Find matching exclude rules
        matching_excludes = [r for r in exclude_rules if _matches_rule(art, r)]
        high_priority_excludes = [r for r in matching_excludes if r["priority"] > 5]

        # Hard exclude: high-priority exclude rule matched
        if high_priority_excludes:
            art["filter_status"] = "excluded"
            continue

        # Check if any include rule matches
        include_matched = any(_matches_rule(art, r) for r in include_rules)

        # Low/medium exclude rules can be overridden by preference score (unless explicit dislike)
        low_prio_excludes = [r for r in matching_excludes if r["priority"] <= 5]
        preference_override = (
            not explicit_dislike
            and pref_score >= 0.7
            and bool(low_prio_excludes)
        )

        if matching_excludes and not preference_override:
            art["filter_status"] = "excluded"
            continue

        if include_matched or pref_score >= 0.7:
            art["filter_status"] = "included"
            art["preference_score"] = pref_score
            accepted.append(art)
        else:
            art["filter_status"] = "excluded"

    return accepted
