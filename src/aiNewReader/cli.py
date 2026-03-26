from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click
import yaml

from .config import load_config, get_config
from .db import get_db, init_db, get_all_feeds, get_all_filter_rules, upsert_filter_rule, delete_filter_rule, get_last_run, upsert_feed


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _run_pipeline(hours: int, provider: str | None, dry_run: bool) -> None:
    from .health import run_health_check, check_ollama
    from .fetcher import fetch_all_feeds, sync_feeds_from_yaml
    from .dedup import deduplicate
    from .extractor import extract_all
    from .classifier import classify_articles
    from .filter import sync_rules_from_yaml, filter_articles
    from .auditor import audit_articles
    from .feedback import compute_preference_scores
    from .renderer import render_digest
    from .rag.store import index_articles_batch
    from .db import create_run, complete_run, insert_article, update_article_embedding, update_article_dedup

    cfg = get_config()
    provider_name = provider or cfg.provider.default

    init_db()

    click.echo("▶ Stage 0: Health check")
    ollama_ok = await check_ollama()
    if not ollama_ok:
        click.echo("  [WARN] Ollama not reachable or bge-m3 not loaded. Semantic dedup disabled.")
    health = await run_health_check(verbose=True)
    click.echo(f"  Feeds: {health['healthy']} healthy, {health['unhealthy']} unhealthy")

    # Sync feeds and filters from YAML
    with open("feeds.yaml", encoding="utf-8") as f:
        feeds_data = yaml.safe_load(f) or {}
    sync_feeds_from_yaml(feeds_data.get("feeds", []))
    sync_rules_from_yaml()

    with get_db() as conn:
        run_id = create_run(conn, hours, provider_name)

    stats: dict[str, int] = {"fetched": 0, "after_dedup": 0, "after_filter": 0, "audited": 0}

    click.echo(f"▶ Stage 1: Fetching feeds (last {hours}h)")
    articles = await fetch_all_feeds(hours)
    click.echo(f"  Fetched: {len(articles)} articles")
    stats["fetched"] = len(articles)

    click.echo("▶ Stage 2: Deduplicating")
    articles = await deduplicate(articles, hours_window=hours)
    originals = [a for a in articles if a.get("dedup_status") == "original"]
    click.echo(f"  After dedup: {len(originals)} (dropped {len(articles) - len(originals)})")
    stats["after_dedup"] = len(originals)

    # Persist articles to DB
    with get_db() as conn:
        for art in articles:
            art_id = insert_article(conn, {**art, "run_id": run_id})
            art["id"] = art_id
            if art.get("dedup_status") != "original":
                update_article_dedup(conn, art_id, art["dedup_status"])
            if art.get("embedding"):
                update_article_embedding(conn, art_id, art["embedding"])

    articles = originals

    click.echo("▶ Stage 3: Extracting content")
    articles = await extract_all(articles)
    click.echo(f"  Extracted {len(articles)} articles")

    # Update DB with content
    with get_db() as conn:
        from .db import update_article_content
        for art in articles:
            update_article_content(conn, art["id"], art.get("markdown_content", ""), art.get("word_count", 0))

    click.echo("▶ Stage 4: Classifying")
    articles = classify_articles(articles, provider_name)
    click.echo(f"  Classified {len(articles)} articles")

    click.echo("▶ Stage 5: Filtering")
    article_ids = [a["id"] for a in articles]
    pref_scores = await compute_preference_scores(article_ids)
    articles = filter_articles(articles, pref_scores)
    click.echo(f"  After filter: {len(articles)}")
    stats["after_filter"] = len(articles)

    click.echo("▶ Stage 6: Auditing long articles")
    articles = audit_articles(articles, cfg.audit_word_threshold, provider_name)
    audited_count = sum(1 for a in articles if a.get("audit_summary"))
    click.echo(f"  Audited: {audited_count}")
    stats["audited"] = audited_count

    # Re-filter post-audit reclassifications
    re_eval = [a for a in articles if a.get("audit_classification_correct") is False]
    if re_eval:
        click.echo(f"  Re-evaluating {len(re_eval)} reclassified articles")
        remaining = filter_articles(re_eval, pref_scores)
        excluded_ids = {a["id"] for a in re_eval} - {a["id"] for a in remaining}
        with get_db() as conn:
            for art in articles:
                if art["id"] in excluded_ids:
                    from .db import update_article_audit
                    conn.execute(
                        "UPDATE articles SET excluded_post_audit=1 WHERE id=?", (art["id"],)
                    )
        articles = [a for a in articles if a["id"] not in excluded_ids]

    click.echo("▶ Stage 6b: Generating daily report")
    from .reporter import generate_report
    from .db import save_report
    report_data = generate_report(articles, provider_name)
    report_json = json.dumps(report_data, ensure_ascii=False)
    with get_db() as conn:
        save_report(conn, run_id, report_json)
    click.echo(f"  Report: {len(report_data.get('key_themes', []))} themes identified")

    click.echo("▶ Indexing to RAG store")
    index_articles_batch(articles)

    click.echo("▶ Stage 7: Rendering digest")
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    output_path_str = cfg.delivery.markdown_output.replace("{date}", date_str)
    output_path = Path(output_path_str)
    render_digest(articles, stats, output_path)
    click.echo(f"  Digest: {output_path}")

    if not dry_run:
        click.echo("▶ Stage 8: Delivery")
        from .delivery.email import send_digest as email_digest
        from .delivery.telegram import send_digest as tg_digest

        if cfg.delivery.email.enabled:
            ok = email_digest(output_path)
            click.echo(f"  Email: {'sent' if ok else 'failed'}")

        if cfg.delivery.telegram.enabled:
            ok = await tg_digest(output_path)
            click.echo(f"  Telegram: {'sent' if ok else 'failed'}")

    with get_db() as conn:
        complete_run(conn, run_id, stats)

    click.echo(f"\n✓ Done. {stats['after_filter']} articles in digest.")


# ── CLI commands ──────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--hours", default=None, type=int, help="Time window in hours (default: from config)")
@click.option("--provider", default=None, help="LLM provider override")
@click.option("--dry-run", is_flag=True, help="Skip delivery step")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
def main(ctx: click.Context, hours: int | None, provider: str | None, dry_run: bool, config_path: str) -> None:
    """aiNewReader — AI-powered RSS digest pipeline."""
    load_config(config_path)
    if ctx.invoked_subcommand is None:
        cfg = get_config()
        h = hours or cfg.hours_window
        asyncio.run(_run_pipeline(h, provider, dry_run))


@main.command()
@click.option("--port", default=None, type=int, help="Port (default: from config)")
@click.option("--host", default=None, help="Host (default: from config)")
def serve(port: int | None, host: str | None) -> None:
    """Start the web dashboard."""
    import uvicorn
    cfg = get_config()
    uvicorn.run(
        "dashboard.app:app",
        host=host or cfg.dashboard.host,
        port=port or cfg.dashboard.port,
        reload=False,
    )


@main.command()
@click.argument("query")
@click.option("--limit", default=10, type=int)
@click.option("--language", default=None)
@click.option("--tag", default=None)
def search(query: str, limit: int, language: str | None, tag: str | None) -> None:
    """Semantic search over stored articles."""
    from .rag.query import search as rag_search

    async def _search() -> None:
        results = await rag_search(query, limit=limit, language=language, tag=tag)
        if not results:
            click.echo("No results.")
            return
        for r in results:
            click.echo(f"\n[{r['pub_date'][:10] if r.get('pub_date') else '?'}] {r['title']}")
            click.echo(f"  {r['url']}")
            click.echo(f"  Tags: {', '.join(r['tags'])}")
            if r.get("snippet"):
                click.echo(f"  {r['snippet'][:200]}")

    asyncio.run(_search())


@main.command()
@click.option("--url", required=True, help="Article URL")
@click.option("--like", "signal", flag_value=1, help="Like this article")
@click.option("--dislike", "signal", flag_value=-1, help="Dislike this article")
def feedback(url: str, signal: int) -> None:
    """Record article feedback."""
    from .feedback import record_feedback

    async def _fb() -> None:
        ok = await record_feedback(url, signal)
        if ok:
            click.echo(f"Feedback recorded ({'like' if signal == 1 else 'dislike'}) for {url}")
        else:
            click.echo(f"Article not found: {url}", err=True)
            sys.exit(1)

    asyncio.run(_fb())


@main.command()
def stats() -> None:
    """Show last run statistics."""
    init_db()
    with get_db() as conn:
        row = get_last_run(conn)
    if row is None:
        click.echo("No runs found.")
        return
    click.echo(f"Last run: {row['started_at']}")
    click.echo(f"  Status: {row['status']}")
    click.echo(f"  Provider: {row['provider']}")
    click.echo(f"  Fetched: {row['articles_fetched']}")
    click.echo(f"  After dedup: {row['articles_after_dedup']}")
    click.echo(f"  After filter: {row['articles_after_filter']}")
    click.echo(f"  Audited: {row['articles_audited']}")
    if row["error_message"]:
        click.echo(f"  Error: {row['error_message']}")


# ── Filter commands ───────────────────────────────────────────────────────────

@main.group()
def filter() -> None:
    """Manage filter rules."""


@filter.command("list")
def filter_list() -> None:
    """List all filter rules."""
    init_db()
    with get_db() as conn:
        rows = get_all_filter_rules(conn)
    if not rows:
        click.echo("No rules.")
        return
    for r in rows:
        status = "✓" if r["enabled"] else "✗"
        tags = json.loads(r["tags"])
        click.echo(f"[{status}] [{r['priority']:2d}] {r['action'].upper():8s} {r['name']}")
        click.echo(f"         Tags: {', '.join(tags)}")


@filter.command("add")
@click.argument("name")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--keywords", default="", help="Comma-separated keywords")
@click.option("--include/--exclude", default=True)
@click.option("--priority", default=5, type=int)
def filter_add(name: str, tags: str, keywords: str, include: bool, priority: int) -> None:
    """Add a filter rule."""
    init_db()
    rule = {
        "name": name,
        "action": "include" if include else "exclude",
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
        "priority": priority,
        "enabled": True,
    }
    with get_db() as conn:
        upsert_filter_rule(conn, rule)
    from .filter import save_rules_to_yaml, load_rules
    with get_db() as conn:
        all_rules = get_all_filter_rules(conn)
    rules_data = [
        {
            "name": r["name"],
            "action": r["action"],
            "tags": json.loads(r["tags"]),
            "keywords": json.loads(r["keywords"]),
            "priority": r["priority"],
            "enabled": bool(r["enabled"]),
        }
        for r in all_rules
    ]
    save_rules_to_yaml(rules_data)
    click.echo(f"Added rule: {name}")


@filter.command("remove")
@click.argument("name")
def filter_remove(name: str) -> None:
    """Remove a filter rule."""
    init_db()
    with get_db() as conn:
        delete_filter_rule(conn, name)
    click.echo(f"Removed rule: {name}")


@filter.command("toggle")
@click.argument("name")
def filter_toggle(name: str) -> None:
    """Toggle a filter rule on/off."""
    init_db()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM filter_rules WHERE name=?", (name,)).fetchone()
        if row is None:
            click.echo(f"Rule not found: {name}", err=True)
            return
        new_state = not bool(row["enabled"])
        conn.execute("UPDATE filter_rules SET enabled=? WHERE name=?", (new_state, name))
    click.echo(f"Rule '{name}' {'enabled' if new_state else 'disabled'}")


# ── Feed commands ─────────────────────────────────────────────────────────────

@main.group()
def feeds() -> None:
    """Manage RSS feeds."""


@feeds.command("list")
def feeds_list() -> None:
    """List all feeds."""
    init_db()
    with get_db() as conn:
        rows = get_all_feeds(conn)
    if not rows:
        click.echo("No feeds.")
        return
    for r in rows:
        enabled = "✓" if r["enabled"] else "✗"
        healthy = "🟢" if r["healthy"] else "🔴"
        click.echo(f"[{enabled}] {healthy} [{r['article_count']:4d}] {r['name'] or r['url']}")
        click.echo(f"             {r['url']}")


@feeds.command("add")
@click.argument("url")
@click.option("--name", default=None)
def feeds_add(url: str, name: str | None) -> None:
    """Add a feed."""
    init_db()
    with get_db() as conn:
        upsert_feed(conn, url, name or url)
    from .fetcher import save_feeds_to_yaml
    save_feeds_to_yaml()
    click.echo(f"Added feed: {url}")


@feeds.command("remove")
@click.argument("url")
def feeds_remove(url: str) -> None:
    """Permanently remove a feed."""
    init_db()
    with get_db() as conn:
        conn.execute("DELETE FROM feeds WHERE url=?", (url,))
    from .fetcher import save_feeds_to_yaml
    save_feeds_to_yaml()
    click.echo(f"Removed: {url}")


@feeds.command("import")
@click.argument("opml_file", type=click.Path(exists=True))
def feeds_import(opml_file: str) -> None:
    """Import feeds from an OPML file."""
    init_db()
    from .fetcher import import_opml
    feeds = import_opml(opml_file)
    click.echo(f"Imported {len(feeds)} feed(s) from {opml_file}")
    for f in feeds:
        click.echo(f"  + {f['name']}  {f['url']}")


@feeds.command("disable")
@click.argument("url")
def feeds_disable(url: str) -> None:
    """Disable a feed."""
    init_db()
    with get_db() as conn:
        conn.execute("UPDATE feeds SET enabled=0 WHERE url=?", (url,))
    click.echo(f"Disabled: {url}")


@feeds.command("enable")
@click.argument("url")
def feeds_enable(url: str) -> None:
    """Enable a feed."""
    init_db()
    with get_db() as conn:
        conn.execute("UPDATE feeds SET enabled=1 WHERE url=?", (url,))
    click.echo(f"Enabled: {url}")
