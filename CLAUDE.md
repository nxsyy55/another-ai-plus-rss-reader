# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable)
pip install -e .
# Windows: if lancedb fails: pip install lancedb --no-build-isolation

# Run full pipeline
python reader.py
python reader.py --hours 48 --provider gemini --dry-run

# Web dashboard (localhost:8080)
python reader.py serve

# Other CLI commands
python reader.py search "query"
python reader.py stats
python reader.py feedback --url "..." --like
python reader.py feeds list|add|remove|import|disable|enable
python reader.py filter list|add|remove|toggle

# Ollama setup (required for embeddings/semantic dedup)
ollama pull bge-m3
ollama serve
```

No dedicated test suite or linter config exists in this project.

## Architecture

**aiNewReader** is a Python 3.12+ CLI + web dashboard that runs a sequential 8-stage pipeline to fetch, deduplicate, classify, filter, audit, and deliver RSS news digests.

### Entry Points

- `reader.py` — thin launcher that adds `src/` to path, delegates to `src/aiNewReader/cli.py`
- `src/aiNewReader/cli.py` — Click CLI; `_run_pipeline()` orchestrates all stages
- `dashboard/app.py` — FastAPI app mounted with route groups from `dashboard/routes/`

### Pipeline Stages (cli.py `_run_pipeline`)

1. **Health** (`health.py`) — HTTP HEAD checks on feeds; verifies Ollama availability
2. **Fetch** (`fetcher.py`) — async RSS fetch with ETag/Last-Modified caching; filters by time window
3. **Dedup** (`dedup.py`) — 3-layer: URL normalization → fuzzy title (rapidfuzz ≥80%) → semantic cosine similarity (bge-m3 embeddings ≥0.92)
4. **Extract** (`extractor.py`) — parallel HTTP fetch + trafilatura markdown extraction (semaphore=10)
5. **Classify** (`classifier.py`) — batched LLM tagging (batch=10) via provider abstraction
6. **Filter** (`filter.py`) — rule-based include/exclude with preference score override (feedback-weighted)
7. **Audit** (`auditor.py`) — LLM summarization + fact-check for articles >500 words; may reclassify
8. **Render** (`renderer.py`) — Jinja2 digest template grouped by primary tag; delivery via email/Telegram

### LLM Provider Abstraction (`src/aiNewReader/providers/`)

All providers implement the `Provider` protocol (`providers/base.py`):
- `classify(articles: list[ArticleInput]) -> list[ClassifyResult]`
- `audit(article: ArticleInput) -> AuditResult`

Implementations: `anthropic.py`, `gemini.py`, `deepseek.py`, `ollama.py`. Provider is selected at runtime via `config.yaml` or `--provider` flag.

### Embeddings & Vector Store

- **Embeddings** (`embeddings.py`): calls Ollama `POST /api/embed` (bge-m3, 1024-dim float32); stored as BLOBs in SQLite using `struct.pack`
- **RAG** (`rag/store.py`, `rag/query.py`): LanceDB at `data/lancedb/`; used for semantic search and dedup; schema includes url, title, tags (JSON string), vector

### Database (`db.py`)

SQLite WAL mode at `data/reader.db`. Core tables: `articles`, `article_tags`, `filter_rules`, `feedback`, `runs`, `feeds`. All pipeline state is persisted here; the dashboard reads from it directly.

### Configuration

- `config.yaml` — global settings, provider/model selection, delivery config
- `feeds.yaml` / `filters.yaml` — synced bidirectionally with DB on CLI startup
- `src/aiNewReader/config.py` — Pydantic models, singleton `get_config()`, env override `AINEWREADER_CONFIG`

### Environment Variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Default provider |
| `GEMINI_API_KEY` | Google Gemini |
| `DEEPSEEK_API_KEY` | DeepSeek |
| `AINEWREADER_CONFIG` | Path to config.yaml |

### Feedback & Preference Scoring (`feedback.py`)

User likes (+1) / dislikes (-1) are stored with article embeddings. `compute_preference_score()` returns a float [-1, 1] based on cosine similarity to centroid of liked vs disliked embeddings. Filter stage uses this to override exclude rules when score ≥ 0.7 and no explicit dislike exists.
