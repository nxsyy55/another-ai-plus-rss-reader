# AI News Reader: Hub Source of Truth

This directory serves as the **"Source of Truth"** for LLM ingestion and RAG (Retrieval-Augmented Generation) applications. It contains standardized JSON exports of curated articles.

---

## 📄 JSON Schema Dictionary (v1.0)

Every file in this folder follows a strict but extensible schema:

| Field | Type | Description |
| :--- | :--- | :--- |
| `article_id` | String | A robust identifier based on the content hash (not a sequential DB ID). |
| `title` | String | Cleaned title of the article. |
| `url` | String | Original source URL. |
| `source` | Object | Metadata about the originating feed (`name`, `url`). |
| `published_at` | ISO-8601 | The article's original publication timestamp. |
| `collected_at` | ISO-8601 | When the article was fetched and processed. |
| `content.markdown`| String | The cleaned, main text content in Markdown format. |
| `content.word_count`| Integer | Total words in the `markdown` content. |
| `content.summary` | String | Initial raw summary or lead paragraph. |
| `enrichment.tags` | Array | AI-assigned tags with `name` and `confidence` score (0-1). |
| `enrichment.audit_summary` | String | Post-processing AI audit summary (concise insight). |
| `enrichment.classification_correct` | Boolean | Verification flag for the original classification. |
| `version` | String | Schema version (currently "1.0"). |

---

## 🛠 Protocols for Evolution

To maintain the integrity of the "Source of Truth," follow these guidelines for updates:

### 1. Extensibility Protocol
*   **Additive Changes:** You can add new fields (e.g., `enrichment.sentiment`) at any time. These will NOT break existing LLM system prompts.
*   **Renaming/Deleting:** Avoid changing existing keys (e.g., don't rename `url` to `link`). If necessary, increment the major version.

### 2. Versioning Protocol
*   **Minor Updates (1.x):** For adding new optional fields or improving data quality (e.g., cleaner markdown).
*   **Major Updates (2.0):** For structural changes that require updating LLM ingestion scripts.

### 3. Update Policy
*   **Manual Edits:** These JSON files can be manually edited (e.g., to fix an AI-generated summary). Manual edits should be treated as the final authority over database records.
*   **Re-exports:** If the backend logic improves, articles can be re-exported. Re-exports will overwrite existing files to ensure the latest "truth" is available.

### 4. Naming Convention
Files are named using a strictly alphanumeric format: `YYYYMMDD[HASH].json` (e.g., `20260331a1b2c3d4e5f6.json`). 
*   This avoids issues with special characters or non-English titles (e.g., Chinese characters).
*   It ensures files are unique, robust, and correctly sorted by date.

---

## 🧠 LLM Ingestion Guide
When feeding these files to an LLM, use the following logic:
1.  **Prioritize Markdown:** The `content.markdown` is the most information-dense field.
2.  **Trust Enrichment:** Use `enrichment.tags` for categorization and `enrichment.audit_summary` for quick context.
3.  **Check Version:** Ensure your parser handles the `version` field to remain compatible with future schema updates.
