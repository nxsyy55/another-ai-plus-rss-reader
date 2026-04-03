from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

DB_PATH = Path("data/reader.db")
SCHEMA_VERSION = 6


def _get_conn(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(path: Path = DB_PATH) -> Generator[sqlite3.Connection, None, None]:
    conn = _get_conn(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path = DB_PATH) -> None:
    with get_db(path) as conn:
        _create_schema(conn)
        _migrate(conn)


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS feeds (
            id               INTEGER PRIMARY KEY,
            url              TEXT UNIQUE NOT NULL,
            name             TEXT,
            enabled          BOOLEAN DEFAULT 1,
            skip_llm         BOOLEAN DEFAULT 0,
            healthy          BOOLEAN DEFAULT 1,
            last_checked     DATETIME,
            last_fetched     DATETIME,
            etag             TEXT,
            last_modified    TEXT,
            article_count    INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS runs (
            id                    INTEGER PRIMARY KEY,
            started_at            DATETIME,
            completed_at          DATETIME,
            hours_window          INTEGER,
            provider              TEXT,
            articles_fetched      INTEGER DEFAULT 0,
            articles_after_dedup  INTEGER DEFAULT 0,
            articles_after_filter INTEGER DEFAULT 0,
            articles_audited      INTEGER DEFAULT 0,
            articles_extraction_failed INTEGER DEFAULT 0,
            status                TEXT DEFAULT 'running',
            error_message         TEXT
        );

        CREATE TABLE IF NOT EXISTS articles (
            id                           INTEGER PRIMARY KEY,
            url                          TEXT UNIQUE NOT NULL,
            title                        TEXT,
            pub_date                     DATETIME,
            feed_id                      INTEGER REFERENCES feeds(id) ON DELETE CASCADE,
            language                     TEXT,
            raw_summary                  TEXT,
            markdown_content             TEXT,
            word_count                   INTEGER,
            content_hash                 TEXT,
            full_content_extracted       BOOLEAN DEFAULT 0,
            embedding                    BLOB,
            run_id                       INTEGER REFERENCES runs(id),
            dedup_status                 TEXT DEFAULT 'original',
            audit_summary                TEXT,
            audit_classification_correct BOOLEAN,
            excluded_post_audit          BOOLEAN DEFAULT 0,
            created_at                   DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS article_tags (
            id         INTEGER PRIMARY KEY,
            article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
            tag        TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            verified   BOOLEAN DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS filter_rules (
            id       INTEGER PRIMARY KEY,
            name     TEXT UNIQUE NOT NULL,
            action   TEXT NOT NULL,
            tags     TEXT DEFAULT '[]',
            keywords TEXT DEFAULT '[]',
            priority INTEGER DEFAULT 5,
            enabled  BOOLEAN DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id         INTEGER PRIMARY KEY,
            article_id INTEGER REFERENCES articles(id),
            signal     INTEGER NOT NULL,
            embedding  BLOB,
            timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reports (
            id           INTEGER PRIMARY KEY,
            run_id       INTEGER REFERENCES runs(id),
            content      TEXT NOT NULL,
            generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_reports (
            id           INTEGER PRIMARY KEY,
            type         TEXT NOT NULL, -- 'article' or 'feed'
            url          TEXT NOT NULL,
            title        TEXT,
            feed_url     TEXT,
            reason       TEXT,
            content      TEXT,
            reported_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
        CREATE INDEX IF NOT EXISTS idx_articles_pub_date ON articles(pub_date);
        CREATE INDEX IF NOT EXISTS idx_articles_run_id ON articles(run_id);
        CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id);
        CREATE INDEX IF NOT EXISTS idx_article_tags_article_id ON article_tags(article_id);
        CREATE INDEX IF NOT EXISTS idx_feedback_article_id ON feedback(article_id);
        CREATE INDEX IF NOT EXISTS idx_reports_run_id ON reports(run_id);
        CREATE INDEX IF NOT EXISTS idx_user_reports_type ON user_reports(type);
    """)


def _get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None:
        return 0
    return int(row["value"])


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )


def _migrate(conn: sqlite3.Connection) -> None:
    current = _get_schema_version(conn)
    if current < 1:
        _set_schema_version(conn, 1)
    if current < 2:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id           INTEGER PRIMARY KEY,
                run_id       INTEGER REFERENCES runs(id),
                content      TEXT NOT NULL,
                generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_run_id ON reports(run_id)")
        _set_schema_version(conn, 2)
    if current < 3:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id)")
        _set_schema_version(conn, 3)
    if current < 4:
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN articles_extraction_failed INTEGER DEFAULT 0")
        except sqlite3.OperationalError: pass
        try:
            conn.execute("ALTER TABLE articles ADD COLUMN full_content_extracted BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError: pass
        _set_schema_version(conn, 4)
    if current < 5:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_reports (
                id           INTEGER PRIMARY KEY,
                type         TEXT NOT NULL,
                url          TEXT NOT NULL,
                title        TEXT,
                feed_url     TEXT,
                reason       TEXT,
                content      TEXT,
                reported_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_reports_type ON user_reports(type)")
        _set_schema_version(conn, 5)
    if current < 6:
        try:
            conn.execute("ALTER TABLE feeds ADD COLUMN skip_llm BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError: pass
        _set_schema_version(conn, 6)


# ── Feed helpers ──────────────────────────────────────────────────────────────

def upsert_feed(conn: sqlite3.Connection, url: str, name: str, enabled: bool = True, skip_llm: bool = False) -> int:
    row = conn.execute("SELECT id FROM feeds WHERE url=?", (url,)).fetchone()
    if row:
        conn.execute(
            "UPDATE feeds SET name=?, enabled=?, skip_llm=? WHERE url=?",
            (name, enabled, skip_llm, url),
        )
        return row["id"]
    cur = conn.execute(
        "INSERT INTO feeds(url, name, enabled, skip_llm) VALUES (?,?,?,?)",
        (url, name, enabled, skip_llm),
    )
    return cur.lastrowid


def get_feed_by_url(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM feeds WHERE url=?", (url,)).fetchone()


def get_all_feeds(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM feeds ORDER BY name").fetchall()


def delete_feed_by_url(conn: sqlite3.Connection, url: str) -> None:
    delete_feeds_batch(conn, [url])


def delete_feeds_batch(conn: sqlite3.Connection, urls: list[str]) -> None:
    if not urls:
        return
    
    # Get all feed IDs for these URLs
    placeholders = ", ".join("?" for _ in urls)
    rows = conn.execute(f"SELECT id FROM feeds WHERE url IN ({placeholders})", urls).fetchall()
    feed_ids = [row["id"] for row in rows]
    
    if not feed_ids:
        return
        
    id_placeholders = ", ".join("?" for _ in feed_ids)
    
    # Delete related data in order
    conn.execute(f"DELETE FROM feedback WHERE article_id IN (SELECT id FROM articles WHERE feed_id IN ({id_placeholders}))", feed_ids)
    conn.execute(f"DELETE FROM article_tags WHERE article_id IN (SELECT id FROM articles WHERE feed_id IN ({id_placeholders}))", feed_ids)
    conn.execute(f"DELETE FROM articles WHERE feed_id IN ({id_placeholders})", feed_ids)
    conn.execute(f"DELETE FROM feeds WHERE id IN ({id_placeholders})", feed_ids)


def report_feed(conn: sqlite3.Connection, url: str, reason: str = "") -> None:
    row = conn.execute("SELECT * FROM feeds WHERE url=?", (url,)).fetchone()
    if not row:
        return
    
    conn.execute(
        "INSERT INTO user_reports(type, url, title, reason, reported_at) VALUES (?,?,?,?,?)",
        ("feed", url, row["name"], reason, datetime.now().isoformat()),
    )
    delete_feed_by_url(conn, url)


def mark_feed_health(conn: sqlite3.Connection, feed_id: int, healthy: bool) -> None:
    conn.execute(
        "UPDATE feeds SET healthy=?, last_checked=? WHERE id=?",
        (healthy, datetime.now().isoformat(), feed_id),
    )


def update_feed_cache(
    conn: sqlite3.Connection, feed_id: int, etag: str | None, last_modified: str | None
) -> None:
    conn.execute(
        "UPDATE feeds SET etag=?, last_modified=?, last_fetched=? WHERE id=?",
        (etag, last_modified, datetime.now().isoformat(), feed_id),
    )


# ── Run helpers ───────────────────────────────────────────────────────────────

def create_run(conn: sqlite3.Connection, hours_window: int, provider: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs(started_at, hours_window, provider) VALUES (?,?,?)",
        (datetime.now().isoformat(), hours_window, provider),
    )
    return cur.lastrowid

def complete_run(conn: sqlite3.Connection, run_id: int, stats: dict[str, Any], status: str = "success", error: str | None = None) -> None:
    conn.execute(
        """UPDATE runs SET
            completed_at=?,
            articles_fetched=?,
            articles_after_dedup=?,
            articles_after_filter=?,
            articles_audited=?,
            articles_extraction_failed=?,
            articles_new=?,
            status=?,
            error_message=?
        WHERE id=?""",
        (
            datetime.now().isoformat(),
            stats.get("fetched", 0),
            stats.get("after_dedup", 0),
            stats.get("extracted") or stats.get("after_filter", 0),
            stats.get("audited", 0),
            stats.get("extraction_failed", 0),
            stats.get("new", 0),
            status,
            error,
            run_id,
        ),
    )



def get_last_run(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()


# ── Article helpers ───────────────────────────────────────────────────────────

def insert_article(conn: sqlite3.Connection, data: dict[str, Any]) -> tuple[int, bool]:
    keys = [
        "url", "title", "pub_date", "feed_id", "language",
        "raw_summary", "markdown_content", "word_count",
        "full_content_extracted", "content_hash", "embedding", "run_id", "dedup_status",
    ]
    cols = ", ".join(k for k in keys if k in data)
    placeholders = ", ".join("?" for k in keys if k in data)
    values = [data[k] for k in keys if k in data]
    cur = conn.execute(
        f"INSERT OR IGNORE INTO articles({cols}) VALUES ({placeholders})",
        values,
    )
    if cur.lastrowid == 0:
        row = conn.execute("SELECT id FROM articles WHERE url=?", (data["url"],)).fetchone()
        return (row["id"] if row else 0, False)
    return (cur.lastrowid, True)


def get_article_by_url(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM articles WHERE url=?", (url,)).fetchone()


def get_articles_for_run(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM articles WHERE run_id=? AND dedup_status='original' ORDER BY pub_date DESC",
        (run_id,),
    ).fetchall()


def get_recent_articles(conn: sqlite3.Connection, hours: int) -> list[sqlite3.Row]:
    from datetime import timedelta
    since = (datetime.now() - timedelta(hours=hours)).isoformat()
    return conn.execute(
        """SELECT * FROM articles
           WHERE pub_date >= ?
           AND dedup_status='original'
           ORDER BY pub_date DESC""",
        (since,),
    ).fetchall()


def update_article_embedding(conn: sqlite3.Connection, article_id: int, embedding: bytes) -> None:
    conn.execute("UPDATE articles SET embedding=? WHERE id=?", (embedding, article_id))


def update_article_content(
    conn: sqlite3.Connection, article_id: int, markdown: str, word_count: int, full_extracted: bool = False, language: str | None = None
) -> None:
    conn.execute(
        "UPDATE articles SET markdown_content=?, word_count=?, full_content_extracted=?, language=? WHERE id=?",
        (markdown, word_count, full_extracted, language, article_id),
    )


def update_article_dedup(conn: sqlite3.Connection, article_id: int, status: str) -> None:
    conn.execute("UPDATE articles SET dedup_status=? WHERE id=?", (status, article_id))


def update_article_audit(
    conn: sqlite3.Connection,
    article_id: int,
    summary: str,
    classification_correct: bool,
    excluded: bool = False,
) -> None:
    conn.execute(
        """UPDATE articles SET
            audit_summary=?,
            audit_classification_correct=?,
            excluded_post_audit=?
           WHERE id=?""",
        (summary, classification_correct, excluded, article_id),
    )

def report_article(conn: sqlite3.Connection, article_id: int, reason: str = "") -> None:
    row = conn.execute("""
        SELECT a.*, f.url as feed_url 
        FROM articles a 
        LEFT JOIN feeds f ON a.feed_id = f.id 
        WHERE a.id=?
    """, (article_id,)).fetchone()
    if not row:
        return
    
    conn.execute(
        "INSERT INTO user_reports(type, url, title, feed_url, reason, content, reported_at) VALUES (?,?,?,?,?,?,?)",
        (
            "article", 
            row["url"], 
            row["title"], 
            row["feed_url"], 
            reason, 
            row["markdown_content"][:2000] if row["markdown_content"] else None,
            datetime.now().isoformat()
        ),
    )
    conn.execute("DELETE FROM articles WHERE id=?", (article_id,))

def get_user_reports(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM user_reports ORDER BY reported_at DESC LIMIT ?",
        (limit,)
    ).fetchall()

def save_report(conn: sqlite3.Connection, run_id: int, content: str) -> int:
    cur = conn.execute(
        "INSERT INTO reports(run_id, content, generated_at) VALUES (?,?,?)",
        (run_id, content, datetime.now().isoformat()),
    )
    return cur.lastrowid


def get_latest_report(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM reports ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()
