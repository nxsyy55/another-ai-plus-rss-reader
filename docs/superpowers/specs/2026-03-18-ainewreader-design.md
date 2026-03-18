# aiNewReader — Design Specification

**Date:** 2026-03-18
**Status:** Approved
**Project dir:** `I:\aiNewReader`

---

## 1. Overview

A lightweight, AI-powered personal RSS reader that runs as a scheduled Python pipeline on Windows. It fetches articles from 50–100 feeds, deduplicates them, classifies and tags them with AI, filters them based on user-defined topic rules, audits long articles (summarize + verify classification), stores everything in a local database with RAG support, and delivers a Markdown digest. A local web dashboard provides monitoring and control.

**Not a hosted service. Not a Docker app. Not a replacement for existing RSS readers.**
This is a personal intelligence tool that reads feeds so you don't have to.

---

## 2. Core Requirements

| # | Requirement |
|---|---|
| R1 | Fetch articles published in the last N hours (default 24, configurable per run) |
| R2 | Remove duplicate articles via 3-layer deduplication |
| R3 | Classify and auto-tag articles using AI (multilingual, no translation) |
| R4 | Filter articles by user-defined topic rules (include/exclude) + learned preferences |
| R5 | Audit articles over a word threshold: summarize + verify classification |
| R6 | Store full Markdown content of each article in DB for RAG retrieval |
| R7 | Deliver a Markdown digest file; optionally email and/or Telegram |
| R8 | Preference learning via article feedback (👍/👎) backed by bge-m3 embeddings |
| R9 | Configurable LLM provider: Anthropic, Gemini, Ollama, DeepSeek |
| R10 | Local web dashboard for monitoring and control (no Runs tab — CLI only) |
| R11 | Full multilingual support — Chinese, English, etc. Tags may be in any language |
| R12 | Dead feed sources detected and skipped automatically |

---

## 3. Architecture

### 3.1 Pipeline Stages

The pipeline runs sequentially, triggered by CLI or Windows Task Scheduler.

```
Stage 0  SOURCE HEALTH CHECK   Validate feed URLs; mark dead sources in DB; Ollama pre-flight check
Stage 1  FEED FETCHER          Parse RSS/Atom feeds with ETag/Last-Modified caching
Stage 2  DEDUPLICATOR          3-layer: URL norm → fuzzy title → semantic (bge-m3)
Stage 3  CONTENT EXTRACTOR     Fetch full page → clean Markdown (trafilatura)
Stage 4  AI CLASSIFIER         Batch LLM: assign #tags + topic scores (language-aware)
Stage 5  FILTER ENGINE         Evaluate YAML rules + preference score; include/exclude
Stage 6  AUDIT AI              Long articles only: summarize + verify classification
Stage 7  RENDERER              Jinja2 → Markdown digest (grouped by topic)
Stage 8  DELIVERY              Write digest file; optional email + Telegram
```

Stages 2 (dedup) runs **before** Stage 3 (content extraction) to avoid fetching pages for articles that will be discarded.

### 3.2 Data Flow

```
feeds.yaml ──► Stage 0 ──► Stage 1 ──► Stage 2 ──► Stage 3
                                                        │
                                              Markdown stored in DB
                                                        │
                                               Stage 4 ──► Stage 5
                                                               │
                                                    Stage 6 (long only)
                                                               │
                                                    Stage 7 ──► Stage 8
                                                               │
                                                   digest-{date}.md
```

### 3.3 Components

| Component | File | Responsibility |
|---|---|---|
| CLI entry point | `reader.py` | Orchestrates pipeline; parses CLI flags |
| Config loader | `src/aiNewReader/config.py` | Loads and validates YAML configs |
| Database | `src/aiNewReader/db.py` | SQLite schema, migrations, queries |
| Source health | `src/aiNewReader/health.py` | Ping feed URLs; mark dead sources; Ollama pre-flight check |
| Feed fetcher | `src/aiNewReader/fetcher.py` | Async RSS/Atom parsing (fastfeedparser) + HTTP caching; max 20 concurrent; 10s timeout per feed |
| Deduplicator | `src/aiNewReader/dedup.py` | 3-layer deduplication |
| Content extractor | `src/aiNewReader/extractor.py` | Page → Markdown via trafilatura |
| Embeddings | `src/aiNewReader/embeddings.py` | bge-m3 via Ollama API (localhost:11434) |
| LLM providers | `src/aiNewReader/providers/` | Abstraction over Anthropic/Gemini/Ollama/DeepSeek |
| Classifier | `src/aiNewReader/classifier.py` | Batch LLM classification + tagging |
| Filter engine | `src/aiNewReader/filter.py` | YAML rule evaluation + preference scoring |
| Audit AI | `src/aiNewReader/auditor.py` | Summarize + verify classification for long articles |
| Feedback | `src/aiNewReader/feedback.py` | Preference learning via embedding cosine drift |
| Renderer | `src/aiNewReader/renderer.py` | Jinja2 → Markdown digest |
| RAG store | `src/aiNewReader/rag/store.py` | LanceDB wrapper (independent, not AnythingLLM) |
| RAG query | `src/aiNewReader/rag/query.py` | Semantic search over stored articles |
| Dashboard app | `dashboard/app.py` | FastAPI web app (localhost:8080) |
| Dashboard routes | `dashboard/routes/` | feeds, filters, articles, settings |
| Email delivery | `src/aiNewReader/delivery/email.py` | SMTP via smtplib (stdlib) |
| Telegram delivery | `src/aiNewReader/delivery/telegram.py` | Telegram Bot API via httpx (no extra dep) |

---

## 4. File Structure

```
I:\aiNewReader\
├── reader.py                   # Thin launcher: imports cli.py and calls cli.main()
├── config.yaml                 # Provider, delivery, thresholds
├── feeds.yaml                  # Feed list (url, name, weight, enabled)
├── filters.yaml                # Topic include/exclude rules (source of truth)
│
├── src\aiNewReader\
│   ├── __init__.py
│   ├── cli.py                  # ALL Click commands live here; reader.py only calls cli.main()
│   ├── config.py               # Config loading + validation (pydantic)
│   ├── db.py                   # SQLite schema, migrations (schema_version in meta table)
│   ├── health.py               # Stage 0: source URL validation + Ollama pre-flight check
│   ├── fetcher.py              # Stage 1: RSS fetching (async, httpx, semaphore=20, timeout=10s)
│   ├── dedup.py                # Stage 2: deduplication (uses articles.embedding from DB)
│   ├── extractor.py            # Stage 3: page → Markdown (trafilatura, computes word_count)
│   ├── embeddings.py           # bge-m3 via Ollama (multilingual, 1024-dim)
│   ├── classifier.py           # Stage 4: LLM classification + tagging
│   ├── filter.py               # Stage 5: filter rule engine
│   ├── auditor.py              # Stage 6: summarize + verify
│   ├── feedback.py             # Preference learning
│   ├── renderer.py             # Stage 7: Markdown renderer
│   │
│   ├── providers\
│   │   ├── __init__.py
│   │   ├── base.py             # Provider Protocol: classify() + audit() only
│   │   ├── anthropic.py
│   │   ├── gemini.py
│   │   ├── ollama.py
│   │   └── deepseek.py
│   │
│   ├── rag\
│   │   ├── __init__.py
│   │   ├── store.py            # LanceDB wrapper
│   │   └── query.py            # Semantic search interface
│   │
│   └── delivery\
│       ├── __init__.py
│       ├── email.py            # SMTP via smtplib (stdlib)
│       └── telegram.py         # Telegram Bot API via httpx (no extra dep)
│
├── dashboard\
│   ├── app.py                  # FastAPI app + static mount
│   └── routes\
│       ├── __init__.py
│       ├── feeds.py            # Feed CRUD
│       ├── filters.py          # Filter rule editor (writes back to filters.yaml)
│       ├── articles.py         # Article browser + feedback
│       └── settings.py        # Config editor
│
├── templates\
│   ├── digest.md.j2            # Markdown digest template
│   └── dashboard\             # HTMX HTML templates
│       ├── base.html
│       ├── index.html          # Overview / last run stats
│       ├── feeds.html
│       ├── filters.html
│       ├── articles.html
│       └── settings.html
│
├── data\
│   ├── reader.db               # SQLite database
│   └── lancedb\                # LanceDB vector store
│
├── output\                     # Generated digests
│   └── digest-{date}.md
│
└── docs\
    └── superpowers\
        └── specs\
            └── 2026-03-18-ainewreader-design.md
```

---

## 5. Data Model (SQLite)

### `feeds`
```sql
id          INTEGER PRIMARY KEY
url         TEXT UNIQUE NOT NULL
name        TEXT
enabled     BOOLEAN DEFAULT 1
healthy     BOOLEAN DEFAULT 1
last_checked DATETIME
last_fetched DATETIME
etag        TEXT
last_modified TEXT
article_count INTEGER DEFAULT 0
```

### `articles`
```sql
id            INTEGER PRIMARY KEY
url           TEXT UNIQUE NOT NULL
title         TEXT
pub_date      DATETIME
feed_id       INTEGER REFERENCES feeds(id)
language      TEXT                     -- detected language code (en, zh, etc.)
raw_summary   TEXT                     -- from RSS feed
markdown_content TEXT                  -- full page extracted as Markdown
word_count    INTEGER                  -- computed by Stage 3 (extractor.py)
content_hash  TEXT                     -- for dedup
embedding     BLOB                     -- bge-m3 1024-dim float32 vector (for dedup Layer 3 + RAG)
run_id        INTEGER REFERENCES runs(id)
dedup_status  TEXT                     -- 'original' | 'duplicate_url' | 'duplicate_fuzzy' | 'duplicate_semantic'
audit_summary TEXT                     -- bullet-point summary (if audited)
audit_classification_correct BOOLEAN   -- did audit confirm classification? (named to match Section 10)
excluded_post_audit BOOLEAN DEFAULT 0  -- true if re-evaluation after audit resulted in exclusion
created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
```

**Note on embedding reuse:** The `articles.embedding` column stores the bge-m3 vector computed during dedup (Layer 3). The same vector is reused when indexing into LanceDB (RAG store) — no double-computation.

**Migration strategy:** `db.py` maintains a `meta` table with a `schema_version` integer. On startup, `db.py` compares the current version against the expected version and runs ordered upgrade functions (e.g., `upgrade_v1_to_v2()`). No external migration tool required.

### `article_tags`
```sql
id             INTEGER PRIMARY KEY
article_id     INTEGER REFERENCES articles(id)
tag            TEXT                    -- may be in any language
confidence     REAL                    -- 0.0–1.0
verified       BOOLEAN DEFAULT 0       -- set true if audit confirms
```

### `filter_rules`
```sql
id        INTEGER PRIMARY KEY
name      TEXT
action    TEXT                         -- 'include' | 'exclude'
tags      TEXT                         -- JSON array of tag strings
keywords  TEXT                         -- JSON array (matched against title)
priority  INTEGER DEFAULT 5            -- range 1–10; higher = evaluated first; 1=lowest, 10=highest
enabled   BOOLEAN DEFAULT 1
```

**Priority scale:** 1 (lowest) to 10 (highest). Rules with priority > 5 are "high priority" — they cannot be overridden by preference score. Default is 5 (medium).

### `feedback`
```sql
id          INTEGER PRIMARY KEY
article_id  INTEGER REFERENCES articles(id)
signal      INTEGER                    -- +1 (like) | -1 (dislike)
embedding   BLOB                       -- bge-m3 1024-dim float32 vector
timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
```

### `runs`
```sql
id                    INTEGER PRIMARY KEY
started_at            DATETIME
completed_at          DATETIME
hours_window          INTEGER
provider              TEXT
articles_fetched      INTEGER
articles_after_dedup  INTEGER
articles_after_filter INTEGER
articles_audited      INTEGER
status                TEXT             -- 'success' | 'partial' | 'failed'
error_message         TEXT
```

---

## 6. LLM Provider Abstraction

All providers implement the same `Provider` Protocol. **Embeddings are NOT part of this Protocol** — embeddings are always handled by `embeddings.py` via bge-m3/Ollama regardless of which LLM provider is active.

```python
class Provider(Protocol):
    def classify(self, articles: list[ArticleInput]) -> list[ClassifyResult]: ...
    def audit(self, article: ArticleInput) -> AuditResult: ...
```

`embeddings.py` is a standalone module (not a provider) that calls Ollama's REST API at `localhost:11434` with the `bge-m3` model. It is used by: deduplicator (Layer 3), feedback scorer, and RAG store indexer.

Provider selection order:
1. CLI flag `--provider <name>` (per-run override)
2. `config.yaml` → `provider.default`
3. Fallback to Ollama if API key missing

**Cost strategy:**
- Classification: use cheap model (Haiku, Gemini Flash, qwen3.5 locally)
- Audit/summarization: use stronger model (Sonnet, Gemini Pro)
- Embeddings: always bge-m3 via Ollama — never billed to any API key
- Anthropic/Gemini: use prompt caching for repeated system prompts (~90% cost reduction)

---

## 7. Deduplication (3-Layer)

Run in order; stop at first match:

| Layer | Method | Cost | Catches |
|---|---|---|---|
| 1 | URL normalization (strip tracking params, normalize scheme) | Free | Exact URL duplicates |
| 2 | Fuzzy title matching via `rapidfuzz` (token_sort_ratio ≥ 80%) | CPU only | Same story, different headline phrasing |
| 3 | Semantic similarity via bge-m3 embeddings (cosine ≥ 0.92) | Ollama local | Paraphrased articles, translations of same event |

Layer 3 runs against articles from the same 24-hour window to keep comparison set small. Embeddings are read from `articles.embedding` (stored during Stage 2 after bge-m3 call) — no re-computation needed.

---

## 8. Content Extraction (Token Saving)

`extractor.py` uses **trafilatura** (F1 score 0.958, actively maintained) to:
- Fetch the full article page
- Strip boilerplate (nav, ads, footers, sidebars)
- Return clean Markdown text

The Markdown is stored in `articles.markdown_content`. This serves two purposes:
1. **Token saving**: classifier and audit AI receive clean Markdown instead of raw HTML — 60–80% fewer tokens
2. **RAG source**: the Markdown is indexed in LanceDB for semantic search

Extraction is skipped if the article URL is behind a paywall or returns a non-200 status; the raw RSS summary is used as fallback.

---

## 9. Classification & Filtering

### filters.yaml Sync Policy
`filters.yaml` is the **canonical source of truth** for filter rules. The `filter_rules` DB table is a runtime cache. On every startup, `filter.py` loads `filters.yaml` and syncs the DB table (upsert by rule name). Dashboard filter edits write to both `filters.yaml` and the DB atomically. This keeps rules version-controllable via git.

### Classification
The AI classifier receives batches of articles (title + first 300 chars of Markdown). The system prompt:
- Defines the tag vocabulary (from `filters.yaml`)
- Instructs: *"Respond in the same language as the article. Do not translate tags or titles."*
- Requests: topic tags (1–5 per article) + confidence scores

### Filter Engine
Rules are evaluated in priority order (highest first). An article is **included** if:
- At least one `include` rule matches AND no higher-priority `exclude` rule matches
- OR its preference score ≥ 0.7 AND the matching exclude rules all have priority ≤ 5

**Preference score vs. exclude rule precedence:**
- Preference score ≥ 0.7 can override **only low/medium-priority exclude rules (priority ≤ 5)**
- Exclude rules with priority > 5 always win, regardless of preference score
- An article with an explicit dislike signal (`feedback.signal = -1`) is **never** promoted by preference score, even if centroid math produces ≥ 0.7 (direct signal overrides computed score)

### Preference Learning
Each feedback signal is stored with the article's bge-m3 embedding. The preference scorer:
1. Computes the centroid of all liked-article embeddings
2. Computes the centroid of all disliked-article embeddings
3. Scores a new article as: `cosine(article_vec, liked_centroid) - cosine(article_vec, disliked_centroid)`
4. Score ranges from -1.0 to +1.0; shown in dashboard and factored into filter decisions

---

## 10. Audit AI

Triggered for articles where `word_count > audit_word_threshold` (default: 500, configurable). `word_count` is computed and stored by Stage 3 (extractor.py) from the extracted Markdown content.

Receives: full `markdown_content`.

Returns:
- `summary`: 3–5 bullet points in the article's original language
- `verified_tags`: confirmed or corrected tag list
- `classification_correct`: boolean

**Post-audit re-evaluation:**
- If `classification_correct` is true: tags confirmed; `audit_classification_correct = TRUE` stored; article proceeds to Stage 7
- If `classification_correct` is false: tags updated in-place; `audit_classification_correct = FALSE` stored; article **immediately re-evaluated by Stage 5** within the same run
- If re-evaluation results in exclusion: article removed from digest; `excluded_post_audit = TRUE` set in DB
- The pipeline is a DAG — Stage 6 has a conditional loop-back to Stage 5 only; never loops back further
- Maximum one re-evaluation per article (no infinite loops)

---

## 11. RAG Store (Independent)

Uses **LanceDB** (Python library, no server, embedded) + **bge-m3** via Ollama for embeddings.

**Completely independent of AnythingLLM** — uses the `lancedb` Python package directly.

Each article is indexed as:
```
{
  "id": article_id,
  "url": url,
  "title": title,
  "language": language,
  "tags": [tag1, tag2],
  "vector": [1024-dim bge-m3 dense embedding],
  "markdown_content": markdown_content
}
```

**bge-m3 produces 1024-dimensional dense vectors.** This dimension is used consistently in: LanceDB schema, `feedback.embedding` BLOB storage, and preference centroid calculations.

Query interface (`rag/query.py`) supports:
- Semantic search: "find articles about quantum computing"
- Filter by tag, date range, language
- Accessible from dashboard Articles tab and CLI: `python reader.py search "..."`

---

## 12. Web Dashboard

**Stack:** FastAPI + HTMX + plain HTML/CSS (no JS framework)
**Runs:** `python reader.py serve` → `http://localhost:8080`
**Tabs:** Overview, Feeds, Filters, Articles, Settings

| Tab | Features |
|---|---|
| **Overview** | Last run stats, pipeline stage counts (fetched → deduped → filtered → audited), feed health summary, preference score distribution |
| **Feeds** | Add/remove/enable/disable feeds, per-feed article counts, health status (green/red) |
| **Filters** | Visual rule editor — add/edit/delete/reorder rules, toggle enabled, mirrors `filters.yaml` |
| **Articles** | Browse by topic/date/language, full article view with tags + audit summary, 👍/👎 feedback buttons, semantic search |
| **Settings** | Provider selection, model names, audit threshold, delivery config (email/Telegram), hours window default |

**No Runs tab** — pipeline runs are triggered exclusively from CLI for safety.

---

## 13. CLI Interface

```bash
# Run pipeline (default: 24h window)
python reader.py

# Override time window
python reader.py --hours 48

# Use specific provider
python reader.py --provider ollama

# Dry run: fetch + classify, no delivery
python reader.py --dry-run

# Start web dashboard
python reader.py serve
python reader.py serve --port 8080

# Semantic search over stored articles
python reader.py search "AI agents and tool use"

# Feedback
python reader.py feedback --url "https://..." --like
python reader.py feedback --url "https://..." --dislike

# Filter management
python reader.py filter list
python reader.py filter add "AI agents" --tags "ai,llm,agents,人工智能" --include
python reader.py filter remove "Music"
python reader.py filter toggle "Politics"

# Feed management
python reader.py feeds list
python reader.py feeds add "https://..." --name "Hacker News"
python reader.py feeds disable "https://..."

# Show last run stats
python reader.py stats
```

---

## 14. Configuration Files

### `config.yaml`
```yaml
hours_window: 24
audit_word_threshold: 500
max_articles_per_run: 300
health_check_interval_hours: 24

provider:
  default: anthropic
  classify_model: claude-haiku-4-5-20251001
  audit_model: claude-sonnet-4-6
  gemini_classify_model: gemini-2.0-flash
  gemini_audit_model: gemini-2.5-pro
  ollama_base_url: http://localhost:11434
  ollama_embed_model: bge-m3
  ollama_chat_model: qwen3.5

delivery:
  markdown_output: ./output/digest-{date}.md
  email:
    enabled: false
    smtp_host: smtp.gmail.com
    smtp_port: 587
    smtp_user: ""
    to: ""
  telegram:
    enabled: false
    bot_token: ""
    chat_id: ""

dashboard:
  port: 8080
  host: localhost
```

### `filters.yaml`
```yaml
rules:
  - name: "AI Agents"
    tags: ["ai", "llm", "agents", "machine-learning", "人工智能"]
    action: include
    priority: 10

  - name: "Science"
    tags: ["science", "research", "physics", "biology", "科学"]
    action: include
    priority: 8

  - name: "Golf"
    tags: ["golf", "高尔夫"]
    action: include
    priority: 7

  - name: "Politics"
    tags: ["politics", "election", "government", "政治"]
    action: exclude
    priority: 9

  - name: "Sports (non-golf)"
    tags: ["sports", "football", "basketball", "soccer", "baseball", "体育"]
    action: exclude
    priority: 9

  - name: "Music"
    tags: ["music", "concert", "album", "音乐"]
    action: exclude
    priority: 8
```

---

## 15. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12+ | Ecosystem, LLM SDKs, async support |
| RSS parsing | fastfeedparser | 25x faster than feedparser; handles RSS/Atom/RDF |
| HTTP client | httpx (async) | Async, HTTP/2, ETag support |
| Content extraction | trafilatura | Best accuracy (F1 0.958), multilingual, maintained |
| LLM: Anthropic | anthropic SDK | Claude Haiku (classify) + Sonnet (audit) |
| LLM: Gemini | google-genai SDK | Flash (classify) + Pro (audit) |
| LLM: Local | Ollama REST API | qwen3.5:9b for classify/audit, bge-m3 for embed |
| LLM: DeepSeek | openai-compatible API | Optional; via openai SDK with base_url override |
| Embeddings | bge-m3 via Ollama | Multilingual, already installed, local/free |
| Fuzzy matching | rapidfuzz | Faster than fuzzywuzzy, same API |
| Vector store | LanceDB (Python lib) | Embedded, no server, already on machine |
| Database | SQLite (stdlib) | Zero-infrastructure, single file |
| Config | PyYAML + pydantic | YAML human-friendly; pydantic for validation |
| CLI | click | Clean Python CLI framework |
| Web framework | FastAPI | Async, auto-docs, lightweight |
| Frontend | HTMX + plain HTML | No JS framework; server-rendered; minimal complexity |
| Templating | Jinja2 | Both Markdown digest and HTML dashboard |
| Scheduling | Windows Task Scheduler | Native, no Python deps |
| Delivery: email | smtplib (stdlib) | Zero extra deps |
| Delivery: Telegram | httpx (already in stack) | Call Telegram Bot API directly; no extra dep |

---

## 16. Out of Scope

- No multi-user support
- No cloud hosting or Docker
- No translation of articles
- No mobile app
- No social/sharing features
- No browser extension
- No web scraping of paywalled content
- AnythingLLM integration (intentionally independent)
