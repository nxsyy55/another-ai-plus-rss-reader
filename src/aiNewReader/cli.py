from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click
import yaml

from .config import load_config, get_config
from .db import get_db, init_db, get_all_feeds, get_last_run, upsert_feed


def _truncate_words(text: str, max_words: int = 2000) -> str:
    words = text.split()
    return " ".join(words[:max_words]) if len(words) > max_words else text

# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _run_pipeline(hours: int, provider: str | None, dry_run: bool) -> None:
    from .health import run_health_check, check_ollama
    from .fetcher import fetch_all_feeds, sync_feeds_from_yaml
    from .dedup import deduplicate
    from .extractor import extract_all
    from .renderer import render_digest
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

    # Sync feeds from YAML
    with open("feeds.yaml", encoding="utf-8") as f:
        feeds_data = yaml.safe_load(f) or {}
    sync_feeds_from_yaml(feeds_data.get("feeds", []))

    with get_db() as conn:
        run_id = create_run(conn, hours, provider_name)

    stats: dict[str, int] = {"fetched": 0, "after_dedup": 0, "extracted": 0}

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
    media_filtered = [a for a in articles if a.get("media_only")]
    articles = [a for a in articles if not a.get("media_only")]
    click.echo(f"  Extracted {len(articles)} articles (dropped {len(media_filtered)} media-only)")

    # Update DB with content
    with get_db() as conn:
        from .db import update_article_content
        for art in articles:
            update_article_content(
                conn, 
                art["id"], 
                art.get("markdown_content", ""), 
                art.get("word_count", 0),
                full_extracted=art.get("full_content_extracted", False)
            )

    stats["extracted"] = len(articles)
    stats["extraction_failed"] = sum(1 for a in articles if not a.get("full_content_extracted", False))

    empty_content = [a for a in articles if not a.get("markdown_content", "").strip()]
    click.echo(f"  Empty content (skipped for report): {len(empty_content)}")
    articles_with_content = [a for a in articles if a.get("markdown_content", "").strip()]

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    scraped_path = Path(f"output/scraped_{date_str}.md")
    scraped_path.parent.mkdir(parents=True, exist_ok=True)
    with open(scraped_path, "w", encoding="utf-8") as f:
        for art in articles:
            f.write(f"# [{art.get('title', 'Unknown Title')}]({art.get('url', '')})\n\n")
            f.write(art.get("markdown_content", "") + "\n\n---\n\n")
    click.echo(f"  Saved combined markdown to {scraped_path}")

    combined_markdown = "\n\n".join(
        f"# [{a.get('title', 'Unknown Title')}]({a.get('url', '')})\n{_truncate_words(a.get('markdown_content', ''))}"
        for a in articles_with_content
    )

    click.echo("▶ Stage 4: Generating daily report")
    from .reporter import generate_report
    from .db import save_report
    report_data = generate_report(combined_markdown, provider_name)
    report_json = json.dumps(report_data, ensure_ascii=False)
    with get_db() as conn:
        save_report(conn, run_id, report_json)
    click.echo(f"  Report: {len(report_data.get('key_themes', []))} themes identified")

    click.echo("▶ Stage 5: Rendering digest")
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    output_path_str = cfg.delivery.markdown_output.replace("{date}", date_str)
    output_path = Path(output_path_str)
    render_digest(articles_with_content, stats, output_path, report_data=report_data)
    click.echo(f"  Digest: {output_path}")

    if not dry_run:
        click.echo("▶ Stage 6: Delivery")
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

    click.echo(f"\n✓ Done. {len(articles)} articles in digest.")


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
    import sys
    import os
    
    # Ensure the current working directory is in sys.path so uvicorn can find dashboard.app
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
        
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
def search(query: str, limit: int, language: str | None) -> None:
    """Semantic search over stored articles."""
    from .rag.query import search as rag_search

    async def _search() -> None:
        results = await rag_search(query, limit=limit, language=language)
        if not results:
            click.echo("No results.")
            return
        for r in results:
            click.echo(f"\n[{r['pub_date'][:10] if r.get('pub_date') else '?'}] {r['title']}")
            click.echo(f"  {r['url']}")
            if r.get("snippet"):
                click.echo(f"  {r['snippet'][:200]}")

    asyncio.run(_search())


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
    if row["error_message"]:
        click.echo(f"  Error: {row['error_message']}")


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
    from .db import delete_feed_by_url
    with get_db() as conn:
        delete_feed_by_url(conn, url)
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


@feeds.command("clean-paywalls")
@click.option("--dry-run", is_flag=True, default=False, help="Identify but do not delete")
def feeds_clean_paywalls(dry_run: bool) -> None:
    """Identify and remove articles that are likely paywall stubs."""
    from .cleaner import clean_paywalls
    init_db()
    
    click.echo("▶ Cleaning paywalled articles...")
    stats = clean_paywalls(dry_run=dry_run)
    
    click.echo(f"  Checked: {stats['checked']} articles")
    click.echo(f"  Identified: {stats['identified']} paywalls")
    
    if not dry_run:
        click.echo(f"  Marked {stats['deleted']} articles as excluded.")
    else:
        click.echo("  [Dry Run] No changes made.")
        
    if stats["polluted_feeds"]:
        click.echo("\nPolluted feeds (top 10):")
        sorted_feeds = sorted(stats["polluted_feeds"].items(), key=lambda x: x[1], reverse=True)
        for feed, count in sorted_feeds[:10]:
            click.echo(f"  - {feed}: {count} articles")
