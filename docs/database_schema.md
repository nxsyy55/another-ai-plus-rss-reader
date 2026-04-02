# Database Schema

This document describes the SQLite database schema used by `aiNewReader`. The database is typically located at `data/reader.db`.

## Tables Overview

### 1. `meta`
Stores metadata about the database itself.
- `key` (TEXT, PRIMARY KEY): The metadata key (e.g., `schema_version`).
- `value` (TEXT): The metadata value.

### 2. `feeds`
Stores information about the RSS/Atom feeds being tracked.
- `id` (INTEGER, PRIMARY KEY): Unique identifier.
- `url` (TEXT, UNIQUE): The feed's URL.
- `name` (TEXT): Display name for the feed.
- `enabled` (BOOLEAN): Whether the feed is active.
- `healthy` (BOOLEAN): Whether the last fetch was successful.
- `last_checked` (DATETIME): Last time the feed was checked for updates.
- `last_fetched` (DATETIME): Last time new articles were successfully fetched.
- `etag` (TEXT): HTTP ETag for caching.
- `last_modified` (TEXT): HTTP Last-Modified header for caching.
- `article_count` (INTEGER): Total articles fetched from this feed.

### 3. `runs`
Tracks each execution of the processing pipeline.
- `id` (INTEGER, PRIMARY KEY): Unique identifier.
- `started_at` (DATETIME): When the run began.
- `completed_at` (DATETIME): When the run finished.
- `hours_window` (INTEGER): The time window (in hours) used for this run.
- `provider` (TEXT): The LLM provider used (e.g., `gemini`, `ollama`).
- `articles_fetched` (INTEGER): Number of articles discovered.
- `articles_after_dedup` (INTEGER): Number of unique articles after deduplication.
- `articles_after_filter` (INTEGER): Number of articles passing filters.
- `articles_audited` (INTEGER): Number of articles processed by the auditor.
- `articles_extraction_failed` (INTEGER): Number of articles where content extraction failed.
- `status` (TEXT): Run status (`running`, `success`, `failed`).
- `error_message` (TEXT): Error details if the run failed.

### 4. `articles`
The main table storing fetched article content and metadata.
- `id` (INTEGER, PRIMARY KEY): Unique identifier.
- `url` (TEXT, UNIQUE): The article's canonical URL.
- `title` (TEXT): Article title.
- `pub_date` (DATETIME): Publication date.
- `feed_id` (INTEGER): Foreign key to `feeds.id` (ON DELETE CASCADE).
- `language` (TEXT): Detected language.
- `raw_summary` (TEXT): Summary from the feed.
- `markdown_content` (TEXT): Extracted full content in Markdown format.
- `word_count` (INTEGER): Number of words in the extracted content.
- `content_hash` (TEXT): Hash for deduplication.
- `full_content_extracted` (BOOLEAN): Whether full text was successfully extracted.
- `embedding` (BLOB): Vector embedding for semantic search/dedup.
- `run_id` (INTEGER): Foreign key to `runs.id`.
- `dedup_status` (TEXT): `original`, `duplicate`, or `near_duplicate`.
- `audit_summary` (TEXT): AI-generated summary/audit notes.
- `audit_classification_correct` (BOOLEAN): Feedback on AI classification.
- `excluded_post_audit` (BOOLEAN): Whether the article was flagged for exclusion (e.g., paywall, low quality).
- `created_at` (DATETIME): Record creation timestamp.

### 5. `article_tags`
Tags assigned to articles by the classifier.
- `id` (INTEGER, PRIMARY KEY): Unique identifier.
- `article_id` (INTEGER): Foreign key to `articles.id` (ON DELETE CASCADE).
- `tag` (TEXT): The tag name.
- `confidence` (REAL): Confidence score from the classifier.
- `verified` (BOOLEAN): Whether the tag was manually verified.

### 6. `reports`
Synthesized reports (digests) generated at the end of a run.
- `id` (INTEGER, PRIMARY KEY): Unique identifier.
- `run_id` (INTEGER): Foreign key to `runs.id`.
- `content` (TEXT): The full Markdown content of the report.
- `generated_at` (DATETIME): Generation timestamp.

### 7. `user_reports`
Stores user-submitted feedback/reports on specific articles or feeds.
- `id` (INTEGER, PRIMARY KEY): Unique identifier.
- `type` (TEXT): `article` or `feed`.
- `url` (TEXT): URL of the reported item.
- `title` (TEXT): Title of the reported item.
- `feed_url` (TEXT): Associated feed URL.
- `reason` (TEXT): Reason for reporting.
- `content` (TEXT): Snippet of content at time of report.
- `reported_at` (DATETIME): Submission timestamp.

### 8. `feedback`
Semantic feedback used to tune the system.
- `id` (INTEGER, PRIMARY KEY): Unique identifier.
- `article_id` (INTEGER): Foreign key to `articles.id`.
- `signal` (INTEGER): User signal (e.g., +1, -1).
- `embedding` (BLOB): Embedding of the article for similarity-based tuning.
- `timestamp` (DATETIME): Feedback timestamp.

### 9. `filter_rules`
Rules for automatically filtering or tagging articles.
- `id` (INTEGER, PRIMARY KEY): Unique identifier.
- `name` (TEXT, UNIQUE): Rule name.
- `action` (TEXT): Action to take (e.g., `exclude`, `tag`).
- `tags` (TEXT): JSON array of tags to match or apply.
- `keywords` (TEXT): JSON array of keywords to match.
- `priority` (INTEGER): Execution priority.
- `enabled` (BOOLEAN): Whether the rule is active.

## Relationships
- `feeds` -> `articles` (One-to-Many)
- `runs` -> `articles` (One-to-Many)
- `runs` -> `reports` (One-to-Many)
- `articles` -> `article_tags` (One-to-Many)
- `articles` -> `feedback` (One-to-Many)
