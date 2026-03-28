# Design: Settings & Statistics Improvements

**Date:** 2026-03-28
**Branch:** main
**Scope:** 5 independent changes to the settings panel, pipeline, and dashboard

---

## 1. Editable Report Prompt in Settings

### What
The `_REPORT_SYSTEM` prompt in `reporter.py` is hardcoded. Expose it as a user-editable field in the Settings panel.

### How
- Add `report_prompt: str` to `AppConfig` in `config.py`, defaulting to the current hardcoded string.
- `reporter.py` reads `get_config().report_prompt` instead of the constant `_REPORT_SYSTEM`.
- Settings page (`settings.html`) adds a `<textarea name="report_prompt">` with the current prompt value, placed above the General section.
- `settings.py` route adds `report_prompt: str = Form(...)` and saves it to `config.yaml`.
- No other changes needed — the prompt is stored in `config.yaml` and loaded at startup like other config fields.

---

## 2. Scraped Content Quality & Token Optimization

### What
Ensure the reporter only receives articles with actual extracted content, and limit per-article input to control token spend.

### How
In `cli.py` `_run_pipeline()`, before building `combined_markdown`:
1. Filter articles to only those where `markdown_content` is non-empty (truthy).
2. Truncate each article's `markdown_content` to a max of **2000 words** (split on whitespace, rejoin) before concatenating into `combined_markdown`.
3. Log count of skipped (empty-content) articles alongside the "Extracted" count.

The DB update (`update_article_content`) already saves the full scraped content for all articles — no change there.

---

## 3. Max Articles Per Source as Config Parameter

### What
The `count >= 10` limit in `fetcher.py` is hardcoded. Make it configurable.

### How
- Add `max_articles_per_source: int = 10` to `AppConfig`.
- `fetch_all_feeds()` passes the value into `_fetch_feed()` as a parameter.
- `_fetch_feed()` uses it instead of the literal `10`.
- Settings page adds a number input for `max_articles_per_source` in the General section.
- `settings.py` route adds `max_articles_per_source: int = Form(10)` and saves to `config.yaml`.

---

## 4. Remove DeepSeek Support

### What
Remove all DeepSeek provider code and references.

### Files to change
- **Delete**: `src/aiNewReader/providers/deepseek.py`
- **`config.py`**: Remove `deepseek_model` from `ProviderConfig`.
- **`providers/__init__.py`**: Remove DeepSeek import and dispatch branch.
- **`settings.html`**: Remove DeepSeek row from providers table; remove `'deepseek'` from the default provider `<select>`.
- **`settings.py`**: Remove `deepseek_model` Form param; remove from `data["provider"]` save block; remove from cleanup list.
- **`app.py`**: Remove `deepseek` key from `_provider_status()`.
- **`config.yaml`**: Remove `deepseek_model` key (done via settings save or manual).

---

## 5. Statistics Panel

### What
A new `/stats/` page in the dashboard with three sections.

### New files
- `dashboard/routes/stats.py` — route + DB queries
- `templates/dashboard/stats.html` — HTML template

### Register in `app.py`
```python
from .routes import stats
app.include_router(stats.router, prefix="/stats", tags=["stats"])
```

Add `<a href="/stats/">Stats</a>` to `base.html` nav.

### Section A — Run Log
Table of all runs from the `runs` table, columns:
- Date (started_at), Provider, Fetched, After-dedup, Extracted, Status, Duration (completed_at − started_at in seconds)

### Section B — Articles Per Source
Query: `SELECT f.name, COUNT(a.id) as cnt FROM articles a JOIN feeds f ON a.feed_id = f.id WHERE a.dedup_status='original' GROUP BY f.id ORDER BY cnt DESC`
Display as a table with: Feed name, Article count, % of total, simple inline bar (CSS width %).

### Section C — Extraction Quality (from last run)
Using the last run's `run_id`:
- Total articles in last run (dedup_status='original')
- Failed extractions: articles where `markdown_content IS NULL OR markdown_content = ''`
- Success rate %

**Word count distribution** (last run articles with content):
Buckets: 0–200, 200–500, 500–1000, 1000–2000, 2000+ words
Query uses `CASE WHEN word_count < 200 THEN '0–200' ...` to group.
Display as a table with count and % per bucket.

### Section D — Today vs. Historical Comparison
Compute from `runs` table (last 30 runs excluding current):
- Avg fetched, avg after-dedup, avg extracted, avg dedup rate (%)
Compare against the latest run values in a side-by-side table.

### Section E — Token Cost Estimate (last run)
- Input tokens ≈ sum of `word_count` for articles sent to reporter × 1.33
- Output tokens: fixed 8192 (max_tokens cap)
- Per-model pricing table (hardcoded USD per 1M tokens, input/output):

| Model | Input $/1M | Output $/1M |
|-------|-----------|------------|
| claude-haiku-4-5-20251001 | 0.80 | 4.00 |
| claude-sonnet-4-6 | 3.00 | 15.00 |
| claude-opus-4-6 | 15.00 | 75.00 |
| gemini-3-flash-preview | 0.075 | 0.30 |
| gemini-3.1-pro-preview | 1.25 | 5.00 |
| qwen3.5:9b (ollama) | 0.00 | 0.00 |

Display: provider/model used, estimated input tokens, estimated output tokens, estimated cost. Add a note: "Approximate — based on word_count × 1.33 for input tokens."

### DB index addition
Add `CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id)` in `db.py` `_create_schema()` and as a migration step (schema version 3).

---

## File Change Summary

| File | Change |
|------|--------|
| `src/aiNewReader/config.py` | Add `report_prompt`, `max_articles_per_source`; remove `deepseek_model` |
| `src/aiNewReader/reporter.py` | Read prompt from config |
| `src/aiNewReader/fetcher.py` | Pass `max_articles_per_source` from config |
| `src/aiNewReader/cli.py` | Filter empty-content articles, truncate at 2000 words, log skipped count |
| `src/aiNewReader/providers/deepseek.py` | **Delete** |
| `src/aiNewReader/providers/__init__.py` | Remove DeepSeek dispatch |
| `src/aiNewReader/db.py` | Add feed_id index, schema version 3 migration |
| `dashboard/app.py` | Register stats router; remove deepseek from provider_status |
| `dashboard/routes/settings.py` | Add/remove form params; save report_prompt, max_articles_per_source; remove deepseek |
| `dashboard/routes/stats.py` | **New** — all stats queries |
| `templates/dashboard/base.html` | Add Stats nav link |
| `templates/dashboard/settings.html` | Add prompt textarea, max_articles_per_source input; remove deepseek |
| `templates/dashboard/stats.html` | **New** — stats page |
