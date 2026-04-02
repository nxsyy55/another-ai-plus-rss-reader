# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Added
- **SQL Query Console**: Execute raw SQL queries directly from the dashboard for advanced database management.
- **Article Filters**: Filter articles in the dashboard by Source, Language (English/Chinese), and Word Count.
- **Language Detection**: Automatically detect and assign language (`en` or `zh`) during article extraction.
- **Database Utilities**: Added scripts for targeted source deletion (`delete_source.py`), YAML synchronization (`sync_feeds_cleanup.py`), and orphaned article cleanup.
- **Enhanced Stats Panel**: Added "Top Sources by Volume" table, simplified word count buckets, and a "New" articles metric in the Run Log to accurately track database growth.
- **Modern Pagination**: Improved dashboard pagination with dynamic ellipses (e.g., `1 ... 4 5 6 ... 10`) for easier navigation of large datasets.
- Database schema documentation (`docs/database_schema.md`).
- Improved support for non-English (CJK) text:
  - Accurate `word_count` logic for Chinese, Japanese, and Korean characters.
  - Enhanced deduplication for Chinese titles using `fuzz.ratio`.
  - Optimized semantic deduplication threshold (0.88) for better cross-lingual results.
### Fixed
- Fixed integer parsing bug when using the "All Sources" filter option in the dashboard.
- Navigation: "Back to Articles" button now correctly preserves previous search and pagination state using browser history.

## [2026-03-31]
### Added
- **Send to Hub**: Feature to export curated articles as standardized JSON files for RAG pipelines and external LLMs.
- Robust naming for hub files (`YYYYMMDD[HASH].json`) to handle non-English titles safely.

## [2026-03-30]
### Added
- **Defuddle Integration**: Integrated Defuddle as the primary high-quality Markdown extractor.
- Added paywall cleaning tools to identify and exclude low-quality/paywalled content.
- `audition_extraction.py` script for comparing extraction quality across different tools.

## [2026-03-29]
### Added
- Batch deletion and database cleaning tools for feed management.
- OPML export functionality.
- Enhanced statistics dashboard with article-per-source distribution and extraction quality metrics.

## [2026-03-28]
### Added
- Pagination for article browsing in the dashboard.
- Semantic search functionality via Ollama/BGE-M3.
- Improved settings UI for provider and model selection.

## [2026-03-27]
### Added
- Daily AI-generated briefing (Digest) with executive summary and key themes.
- Support for multiple LLM providers: Anthropic, Google Gemini, and Ollama.
- Automatic semantic deduplication using BGE-M3 embeddings.
