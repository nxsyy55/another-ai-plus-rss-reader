# aiNewReader

An RSS news aggregator that produces a daily AI-generated briefing from your subscribed feeds.

## How it works

Fetch articles from RSS feeds → deduplicate → scrape full text → combine everything into one markdown document → send to a single LLM call → get back a structured daily report with an executive summary, key themes, and notable picks.

One LLM call per run. Works with local Ollama (Qwen), Gemini Flash, Claude Haiku, or any other cheap/fast model.

The report is saved as a markdown digest and viewable in the web dashboard.

---

## Prerequisites

- Python 3.12+
- (Optional) [Ollama](https://ollama.com) with `bge-m3` for semantic deduplication

---

## Install

```bash
git clone <repo-url>
cd aiNewReader
uv sync
```

---

## Configure

**1. Set your LLM API key** — create a `.env` file in the project root:

```bash
# Pick one:
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...
# Or use Ollama (no key needed) — set provider.default: ollama in config.yaml
```

**2. Add your feeds** — copy the example and edit:

```bash
cp feeds.yaml.example feeds.yaml
```

Then edit `feeds.yaml`, or use the CLI:

```bash
uv run ainewreader feeds add "https://news.ycombinator.com/rss" --name "Hacker News"
uv run ainewreader feeds import myfeeds.opml   # import from Feedly/Inoreader OPML export
```

**3. (Optional) Start Ollama** for semantic dedup — skipped gracefully if unavailable:

```bash
ollama pull bge-m3
ollama serve
```

---

## Run

```bash
uv run ainewreader                    # fetch last 24h, generate report
uv run ainewreader --hours 48         # custom time window
uv run ainewreader --provider gemini  # override provider for this run
uv run ainewreader --dry-run          # skip delivery
```

Output is saved to `output/digest-YYYY-MM-DD.md`.

---

## Dashboard

```bash
uv run ainewreader serve
```

Open **http://localhost:8080** to browse articles, manage feeds, configure settings, and view pipeline statistics.

Dashboard pages:
- **Daily Report** — executive summary, key themes, notable picks from the latest run
- **Settings** — provider/model selection, editable report prompt, per-source article cap
- **Feeds** — add/remove/disable RSS feeds
- **Articles** — browse all ingested articles with semantic search
- **Stats** — run log, articles-per-source distribution, extraction quality, token cost estimate

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
