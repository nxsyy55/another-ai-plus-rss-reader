# Develop
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

## Common errors

| Error | Fix |
|---|---|
| `ModuleNotFoundError` | Run `uv sync` again |
| `AuthenticationError` | API key missing or wrong in `.env` |
| Semantic dedup skipped | Normal — Ollama not running; URL + fuzzy dedup still active |
| 0 articles in digest | All filtered by dedup or media-only filter — try `--hours 48` |
