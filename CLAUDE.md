# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install and sync dependencies
uv sync

# Run full pipeline
uv run ainewreader
uv run ainewreader --hours 48 --provider gemini --dry-run

# Web dashboard (localhost:8080)
uv run ainewreader serve

# Other CLI commands
uv run ainewreader search "query"
uv run ainewreader stats
uv run ainewreader feedback --url "..." --like
uv run ainewreader feeds list|add|remove|import|disable|enable
uv run ainewreader filter list|add|remove|toggle

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

**Key rule**: All API keys are stored in `.env` at the project root. `config.py` loads it with `load_dotenv(override=True)` so `.env` values **always win over system/user environment variables**. Never rely on Windows system environment variables for API keys — they can hold stale/invalid values that silently override the correct `.env` keys.

### Known Gotchas

#### Gemini provider (recurring — has bitten twice)
1. **`load_dotenv()` without `override=True`**: Windows user-level env vars (`HKCU\Environment`) silently override `.env`. Always use `load_dotenv(override=True)`. If a provider returns "API key not valid", check `[System.Environment]::GetEnvironmentVariable('GEMINI_API_KEY', 'User')` for a stale key before touching code.
2. **Gemini JSON mode requires a top-level object**: `response_mime_type="application/json"` rejects bare top-level arrays. Classify must use `{"articles": [...]}` wrapper, not `[...]` directly. Audit is safe since it already returns `{...}`.
3. **Always pass `api_key=` explicitly** to `genai.Client(api_key=...)` — do not rely on implicit env var pickup alone.
4. **Current Gemini model names** (check `config.yaml` for truth — do NOT invent or guess model names):
   - Classify: `gemini-3-flash-preview`
   - Audit: `gemini-3.1-pro-preview`
   - When adding hardcoded model lists to the UI, always read from `config.yaml` first and verify against the user before listing alternatives.

#### Ollama provider
- Model name must include the tag (e.g. `qwen3.5:9b`, not `qwen3.5`). A missing tag causes a 404 from `/api/chat`.

### Feedback & Preference Scoring (`feedback.py`)

User likes (+1) / dislikes (-1) are stored with article embeddings. `compute_preference_score()` returns a float [-1, 1] based on cosine similarity to centroid of liked vs disliked embeddings. Filter stage uses this to override exclude rules when score ≥ 0.7 and no explicit dislike exists.
