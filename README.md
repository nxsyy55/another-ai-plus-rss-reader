# aiNewReader

## Prerequisites

- Python 3.12+
- (Optional) [Ollama](https://ollama.com) with `bge-m3` for semantic dedup + RAG

---

## 1. Install dependencies

```bash
git clone <repo-url>
cd aiNewReader
uv sync
```


---

## 2. Set your LLM API key

Pick one provider. Default is **Anthropic**.

Create a `.env` file in the project root:

```bash
# Anthropic (default)
ANTHROPIC_API_KEY=sk-ant-...

# Gemini — also edit config.yaml: provider.default: gemini
GEMINI_API_KEY=...

# DeepSeek — also edit config.yaml: provider.default: deepseek
DEEPSEEK_API_KEY=...

# Fully local (no API key) — edit config.yaml: provider.default: ollama
# requires Ollama running with a chat model e.g. qwen3.5
```

---

## 3. (Optional) Start Ollama with bge-m3

Required for semantic deduplication and RAG search. Skipped gracefully if unavailable.

```bash
ollama pull bge-m3
ollama serve
```

---

## 4. Add your feeds

**Option A — Import an OPML file** (exported from Feedly, Inoreader, NewsBlur, etc.):
```bash
python reader.py feeds import myfeeds.opml
```

**Option B — Add feeds one by one:**
```bash
uv run ainewreader feeds add "https://news.ycombinator.com/rss" --name "Hacker News"
uv run ainewreader feeds add "https://feeds.feedburner.com/oreilly/radar" --name "O'Reilly Radar"
```

**Option C — Edit `feeds.yaml` directly**, then feeds sync automatically on next run.

---

## 5. Sanity check

```bash
uv run ainewreader feeds list     # confirm feeds loaded
uv run ainewreader filter list    # confirm filter rules loaded
uv run ainewreader stats          # should say "No runs yet"
```

---

## 6. Dry run (no delivery)

Fetches, deduplicates, classifies, filters, and writes the digest — but skips email/Telegram delivery.

```bash
uv run ainewreader --dry-run
```

Watch the stage output:
```
▶ Stage 0: Health check
▶ Stage 1: Fetching feeds (last 24h)
▶ Stage 2: Deduplicating
▶ Stage 3: Extracting content
▶ Stage 4: Classifying
▶ Stage 5: Filtering
▶ Stage 6: Auditing long articles
▶ Stage 7: Rendering digest
✓ Done. N articles in digest.
```

Check the output:
```bash
cat output/digest-$(date +%Y-%m-%d).md
```

---

## 7. Start the dashboard

```bash
uv run ainewreader serve
```

Open **http://localhost:8080**

| Tab | What you can do |
|---|---|
| Overview | Last run stats, feed health |
| Feeds | Add/remove/disable feeds, import OPML |
| Filters | Add/edit/delete topic rules |
| Articles | Browse, search, give 👍👎 feedback |
| Settings | Change provider, models, thresholds |

---

## 8. Run for real

```bash
uv run ainewreader                    # 24h window (default)
uv run ainewreader --hours 48         # custom window
uv run ainewreader --provider gemini  # override provider for this run
```

---

## Common errors

| Error | Fix |
|---|---|
| `ModuleNotFoundError` | Run `pip install -e .` again |
| `anthropic.AuthenticationError` | `ANTHROPIC_API_KEY` not set |
| `lancedb` build fails | `pip install lancedb --no-build-isolation` |
| Semantic dedup skipped | Normal — Ollama not running; layers 1+2 still work |
| 0 articles in digest | All filtered out — check `python reader.py filter list` and relax rules |
| Dead feeds | Run `python reader.py feeds list` — red feeds are skipped automatically |

---

## CLI reference

```bash
python reader.py                            # run pipeline
python reader.py --hours 48 --dry-run       # dry run, 48h window
python reader.py --provider ollama          # use Ollama for this run
python reader.py serve                      # start dashboard (localhost:8080)
python reader.py search "AI agents"         # semantic search
python reader.py stats                      # last run stats
python reader.py feedback --url "..." --like
python reader.py feedback --url "..." --dislike

python reader.py feeds list
python reader.py feeds add "https://..." --name "My Feed"
python reader.py feeds import myfeeds.opml
python reader.py feeds remove "https://..."
python reader.py feeds disable "https://..."

python reader.py filter list
python reader.py filter add "Topic" --tags "tag1,tag2" --include --priority 8
python reader.py filter remove "Topic"
python reader.py filter toggle "Topic"
```

---

## Scheduling

**Linux/macOS (cron):**
```bash
# Run daily at 7am
0 7 * * * cd /path/to/aiNewReader && uv run ainewreader --hours 24
```

**Windows (Task Scheduler):**
```
Program: uv
Arguments: run ainewreader --hours 24
Start in: C:\path\to\aiNewReader
```
