# aiNewReader

An RSS news aggregator that produces a daily AI-generated briefing from your subscribed feeds.

## How it works

Fetch articles from RSS feeds → deduplicate → scrape full text → combine everything into one markdown document → send to a single LLM call → get back a structured daily report with an executive summary, key themes, and notable picks.

One LLM call per run. Works with local Ollama (Qwen), Gemini Flash, Claude Haiku, or any other cheap/fast model.

The report is saved as a markdown digest and viewable in the web dashboard.

---

## Prerequisites

- Python 3.12+
- **Node.js 20+** (Required for high-quality content extraction)
- **[Defuddle](https://github.com/kepano/defuddle)** (Installed via `npm install -g defuddle`)
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
uv run ainewreader feeds clean-paywalls # remove low-quality/paywalled articles
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
- **Settings** — provider/model selection, editable report prompt, per-source article cap, and **Data Management tools** (paywall cleaning)
- **Feeds** — manage RSS feeds (supports batch deletion)
- **Articles** — browse all ingested articles with semantic search
- **Stats** — run log, articles-per-source distribution, extraction quality, token cost estimate
