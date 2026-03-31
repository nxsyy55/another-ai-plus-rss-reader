from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aiNewReader.db import get_db, init_db
from aiNewReader.config import get_config

router = APIRouter()
templates = Jinja2Templates(directory="templates/dashboard")

PRICING = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (15.00, 75.00),
    "gemini-3-flash-preview": (0.075, 0.30),
    "gemini-3.1-pro-preview": (1.25, 5.00),
    "gemini-3-flash": (0.075, 0.30),
}

BUCKET_ORDER = ["0-200", "200-500", "500-1000", "1000-2000", "2000+"]


@router.get("/", response_class=HTMLResponse)
async def stats_page(request: Request):
    init_db()
    with get_db() as conn:
        # Last 20 runs
        run_rows = conn.execute("""
            SELECT id, started_at, completed_at, provider, articles_fetched,
                   articles_after_dedup, articles_after_filter, articles_extraction_failed, status,
                   CAST(ROUND((JULIANDAY(COALESCE(completed_at, started_at)) - JULIANDAY(started_at)) * 86400) AS INTEGER) as duration_seconds
            FROM runs ORDER BY started_at DESC LIMIT 20
        """).fetchall()

        runs = [dict(r) for r in run_rows]
        last_run = runs[0] if runs else None
        last_run_id = last_run["id"] if last_run else None

        # Articles per source (all-time originals)
        source_rows = conn.execute("""
            SELECT f.name, f.url, COUNT(a.id) as cnt
            FROM articles a JOIN feeds f ON a.feed_id = f.id
            WHERE a.dedup_status='original'
            GROUP BY f.id ORDER BY cnt DESC
        """).fetchall()

        total_articles = sum(r["cnt"] for r in source_rows) or 1
        articles_per_source = [
            {
                "name": r["name"] or r["url"],
                "url": r["url"],
                "cnt": r["cnt"],
                "pct": round(r["cnt"] / total_articles * 100, 1),
            }
            for r in source_rows
        ]

        # Stats that depend on last_run
        extraction_stats = {"total": 0, "failed": 0, "success_rate_pct": 0.0}
        word_buckets: list[dict] = []
        hist_stats = {"avg_fetched": None, "avg_dedup": None, "avg_extracted": None}
        token_estimate = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "model": "", "provider": ""}

        if last_run_id is not None:
            # Extraction stats for last run
            ext_row = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN full_content_extracted=0 THEN 1 ELSE 0 END) as failed
                FROM articles WHERE run_id=? AND dedup_status='original'
            """, (last_run_id,)).fetchone()

            if ext_row and ext_row["total"]:
                total_ext = ext_row["total"]
                failed_ext = ext_row["failed"] or 0
                success_rate = round((total_ext - failed_ext) / total_ext * 100, 1) if total_ext else 0.0
                extraction_stats = {
                    "total": total_ext,
                    "failed": failed_ext,
                    "success_rate_pct": success_rate,
                }

            # Word count distribution for last run
            wc_rows = conn.execute("""
                SELECT
                  CASE
                    WHEN word_count < 200 THEN '0-200'
                    WHEN word_count < 500 THEN '200-500'
                    WHEN word_count < 1000 THEN '500-1000'
                    WHEN word_count < 2000 THEN '1000-2000'
                    ELSE '2000+'
                  END as bucket,
                  COUNT(*) as cnt
                FROM articles
                WHERE run_id=? AND dedup_status='original'
                  AND markdown_content IS NOT NULL AND markdown_content != ''
                GROUP BY bucket
            """, (last_run_id,)).fetchall()

            wc_map = {r["bucket"]: r["cnt"] for r in wc_rows}
            wc_total = sum(wc_map.values()) or 1
            word_buckets = [
                {
                    "bucket": b,
                    "cnt": wc_map.get(b, 0),
                    "pct": round(wc_map.get(b, 0) / wc_total * 100, 1),
                }
                for b in BUCKET_ORDER
            ]

            # Historical averages (last 30 successful runs excluding most recent)
            hist_row = conn.execute("""
                SELECT AVG(articles_fetched) as avg_fetched,
                       AVG(articles_after_dedup) as avg_dedup,
                       AVG(articles_after_filter) as avg_extracted
                FROM (SELECT * FROM runs WHERE status='success' AND id != ?
                      ORDER BY started_at DESC LIMIT 30)
            """, (last_run_id,)).fetchone()

            if hist_row:
                hist_stats = {
                    "avg_fetched": round(hist_row["avg_fetched"]) if hist_row["avg_fetched"] is not None else None,
                    "avg_dedup": round(hist_row["avg_dedup"]) if hist_row["avg_dedup"] is not None else None,
                    "avg_extracted": round(hist_row["avg_extracted"]) if hist_row["avg_extracted"] is not None else None,
                }

            # Token cost estimate for last run
            wsum_row = conn.execute("""
                SELECT COALESCE(SUM(word_count), 0) as word_sum
                FROM articles
                WHERE run_id=? AND dedup_status='original'
                  AND markdown_content IS NOT NULL AND markdown_content != ''
            """, (last_run_id,)).fetchone()

            word_sum = wsum_row["word_sum"] if wsum_row else 0
            input_tokens = int(word_sum * 1.33)
            output_tokens = 8192

            provider = last_run.get("provider", "")
            cfg = get_config()
            model = ""
            if provider == "anthropic":
                model = cfg.provider.anthropic_model
            elif provider == "gemini":
                model = cfg.provider.gemini_model
            elif provider == "ollama":
                model = cfg.provider.ollama_chat_model

            in_price, out_price = PRICING.get(model, (0.0, 0.0))
            cost_usd = (input_tokens / 1_000_000 * in_price) + (output_tokens / 1_000_000 * out_price)

            token_estimate = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd,
                "model": model,
                "provider": provider,
            }

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "runs": runs,
        "last_run": last_run,
        "articles_per_source": articles_per_source,
        "extraction_stats": extraction_stats,
        "word_buckets": word_buckets,
        "hist_stats": hist_stats,
        "token_estimate": token_estimate,
    })
