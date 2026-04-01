# Develop

---

## Architecture Overview

aiNewReader is built as a modular pipeline with a SQLite backend:

1. **Fetcher**: Polling RSS feeds and normalizing entries.
2. **Extractor**: Multi-stage content extraction using Defuddle (Node.js) and Trafilatura.
3. **Deduplicator**: 3-layer deduplication (URL normalization, fuzzy title matching, and BGE-M3 semantic similarity).
4. **Classifier/Tagger**: Batch processing articles through LLM providers for thematic tagging.
5. **Reporter**: Final LLM call to synthesize the daily digest from curated articles.
6. **Dashboard**: Flask-based web interface for reading, searching, and managing the pipeline.

---

## Development Workflow

1. **Run in Dev Mode**: 
   Use `uv run ainewreader serve` for the dashboard and `uv run ainewreader` for the pipeline.
2. **Database**: 
   The SQLite database is located at `data/db.sqlite` (or configured path). You can use `sqlite3` or any GUI tool to inspect it.
3. **Adding a Provider**: 
   Implement the `BaseProvider` interface in `src/aiNewReader/providers/`.
4. **UI Changes**: 
   Templates are located in `templates/dashboard/`. We prefer vanilla CSS and minimal JS for performance and simplicity.

---

## CLI reference

```bash
uv run ainewreader                          # run pipeline
uv run ainewreader --hours 48 --dry-run
uv run ainewreader --provider ollama
uv run ainewreader serve                    # dashboard
uv run ainewreader search "query"           # semantic search
uv run ainewreader stats                    # last run stats

uv run ainewreader feeds list
uv run ainewreader feeds add "https://..."
uv run ainewreader feeds import feeds.opml
uv run ainewreader feeds remove "https://..."
uv run ainewreader feeds disable "https://..."
uv run ainewreader feeds enable "https://..."
uv run ainewreader feeds clean-paywalls     # exclude paywalled articles
```

---

## Scheduling

**Linux/macOS:**
```bash
0 7 * * * cd /path/to/aiNewReader && uv run ainewreader --hours 24
```

**Windows (Task Scheduler):**
```
Program: uv
Arguments: run ainewreader --hours 24
Start in: C:\path\to\aiNewReader
```

---

## Environment variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic / Claude |
| `GEMINI_API_KEY` | Google Gemini |
| `AINEWREADER_CONFIG` | Path to config.yaml (default: `config.yaml`) |

---

## Configuration (`config.yaml`)

The hub feature can be configured in your `config.yaml`:

```yaml
hub:
  enabled: true
  path: "./hub"  # Directory for JSON exports
```

---

## External Dependencies

The pipeline relies on several external tools for specialized tasks:

| Dependency | Purpose | Install Command |
| --- | --- | --- |
| **Node.js** | Runtime for extraction tools | [nodejs.org](https://nodejs.org/) |
| **Defuddle** | Primary Markdown extraction | `npm install -g defuddle` |
| **Ollama** | Semantic dedup & search | [ollama.com](https://ollama.com/) |

---

## Common errors

| Error | Fix |
|---|---|
| `ModuleNotFoundError` | Run `uv sync` again |
| `AuthenticationError` | API key missing or wrong in `.env` |
| Defuddle skipped | Ensure `defuddle` is in your PATH (`npm install -g defuddle`) |
| Semantic dedup skipped | Normal — Ollama not running; URL + fuzzy dedup still active |
| 0 articles in digest | All filtered by dedup or media-only filter — try `--hours 48` |
