from __future__ import annotations

import asyncio
import json
import re
import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from aiNewReader.db import get_db, init_db
from aiNewReader.config import get_config
from ..templates import templates

router = APIRouter()


def slugify(text: str) -> str:
    # Convert to lowercase
    text = text.lower()
    # Remove non-english letters (keep a-z and spaces/hyphens for now to convert to hyphens)
    text = re.sub(r"[^a-z\s-]", "", text)
    # Replace spaces and multiple hyphens with a single hyphen
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text


@router.get("/", response_class=HTMLResponse)
async def articles_page(
    request: Request,
    q: str = Query(default=""),
    feed_id: str = Query(default=None),
    word_bucket: str = Query(default=None),
    language: str = Query(default=None),
    page: int = Query(default=1),
):
    init_db()
    limit = 20
    offset = (page - 1) * limit

    with get_db() as conn:
        # Get feeds for the dropdown
        feeds = conn.execute("SELECT id, name FROM feeds ORDER BY name").fetchall()
        
        where = "WHERE dedup_status='original'"
        params: list = []
        if q:
            where += " AND (title LIKE ? OR markdown_content LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])
        
        parsed_feed_id = None
        if feed_id and feed_id.isdigit():
            parsed_feed_id = int(feed_id)
            where += " AND feed_id = ?"
            params.append(parsed_feed_id)
            
        if language:
            where += " AND language = ?"
            params.append(language)
            
        if word_bucket:
            if word_bucket == "0-200":
                where += " AND word_count < 200"
            elif word_bucket == "200-500":
                where += " AND word_count >= 200 AND word_count < 500"
            elif word_bucket == "500+":
                where += " AND word_count >= 500"

        rows = conn.execute(
            f"SELECT * FROM articles {where} ORDER BY pub_date DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM articles {where}", params
        ).fetchone()
        total = total_row["cnt"] if total_row else 0
        articles = [dict(row) for row in rows]
        
        if q:
            q_lower = q.lower()
            for art in articles:
                if not art.get("snippet"):
                    content = art.get("markdown_content") or ""
                    idx = content.lower().find(q_lower)
                    if idx != -1:
                        start = max(0, idx - 50)
                        end = min(len(content), idx + 250)
                        snippet = content[start:end]
                        if start > 0: snippet = "..." + snippet
                        if end < len(content): snippet += "..."
                        art["snippet"] = snippet
                    else:
                        art["snippet"] = content[:300] + ("..." if len(content) > 300 else "")

    total_pages = max(1, (total + limit - 1) // limit)
    
    pagination = []
    if total_pages <= 7:
        pagination = list(range(1, total_pages + 1))
    else:
        if page <= 4:
            pagination = [1, 2, 3, 4, 5, "...", total_pages]
        elif page >= total_pages - 3:
            pagination = [1, "...", total_pages - 4, total_pages - 3, total_pages - 2, total_pages - 1, total_pages]
        else:
            pagination = [1, "...", page - 1, page, page + 1, "...", total_pages]

    return templates.TemplateResponse("articles.html", {
        "request": request,
        "articles": articles,
        "feeds": [dict(f) for f in feeds],
        "feed_id": parsed_feed_id,
        "word_bucket": word_bucket,
        "language": language,
        "q": q,
        "page": page,
        "total": total,
        "total_pages": total_pages,
        "pagination": pagination,
        "has_next": offset + limit < total,
        "has_prev": page > 1,
    })


@router.get("/{article_id}", response_class=HTMLResponse)
async def article_detail(request: Request, article_id: int):
    init_db()
    with get_db() as conn:
        row = conn.execute("""
            SELECT a.*, f.name as feed_name, f.url as feed_url
            FROM articles a
            LEFT JOIN feeds f ON a.feed_id = f.id
            WHERE a.id = ?
        """, (article_id,)).fetchone()
        if not row:
            return HTMLResponse(content="Article not found", status_code=404)
        article = dict(row)
    
    return templates.TemplateResponse("article_detail.html", {
        "request": request,
        "article": article,
    })


@router.post("/{article_id}/refetch")
async def refetch_article(article_id: int):
    import httpx
    from aiNewReader.extractor import extract_article
    from aiNewReader.db import update_article_content
    
    init_db()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if not row:
            return JSONResponse({"status": "error", "message": "Article not found"}, status_code=404)
        article = dict(row)

    config = get_config()
    
    async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": "aiNewReader/0.1"}) as client:
        # Pass a mutable dict to extract_article, it populates it
        # Note: We set markdown_content to None to force re-extraction in extract_article
        article_to_extract = dict(article)
        article_to_extract["markdown_content"] = None 
        
        extracted = await extract_article(client, article_to_extract)

    with get_db() as conn:
        update_article_content(
            conn, 
            article_id, 
            extracted.get("markdown_content", ""), 
            extracted.get("word_count", 0), 
            extracted.get("full_content_extracted", False),
            extracted.get("language", "en")
        )
        
    return {"status": "success", "message": "Article refetched successfully."}


@router.post("/{article_id}/report")
async def report_article_route(article_id: int, reason: str = Form("")):
    from aiNewReader.db import report_article
    with get_db() as conn:
        report_article(conn, article_id, reason)
    return RedirectResponse(url="/articles/", status_code=303)


@router.post("/{article_id}/send-to-hub")
async def send_to_hub(article_id: int):
    config = get_config()
    if not config.hub.enabled:
        return JSONResponse({"status": "error", "message": "Hub is disabled in config"}, status_code=400)

    hub_path = Path(config.hub.path)
    hub_path.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        # Fetch article
        art_row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if not art_row:
            return JSONResponse({"status": "error", "message": "Article not found"}, status_code=404)
        article = dict(art_row)

        # Fetch feed info
        feed_row = conn.execute("SELECT * FROM feeds WHERE id = ?", (article["feed_id"],)).fetchone()
        feed = dict(feed_row) if feed_row else {}

        # Fetch tags
        tag_rows = conn.execute("SELECT tag, confidence FROM article_tags WHERE article_id = ?", (article_id,)).fetchall()
        tags = [{"name": row["tag"], "confidence": row["confidence"]} for row in tag_rows]

    # Construct robust article_id (independent of DB auto-increment)
    # Using URL hash ensures it is unique and reproducible across systems
    url_hash = hashlib.sha256(article["url"].encode()).hexdigest()
    article_id_str = f"art{url_hash[:16]}"

    # Construct JSON object
    hub_data = {
        "article_id": article_id_str,
        "title": article["title"],
        "url": article["url"],
        "source": {
            "name": feed.get("name"),
            "url": feed.get("url")
        },
        "published_at": article["pub_date"].isoformat() if isinstance(article["pub_date"], datetime) else article["pub_date"],
        "collected_at": article["created_at"].isoformat() if isinstance(article["created_at"], datetime) else article["created_at"],
        "content": {
            "markdown": article["markdown_content"],
            "word_count": article["word_count"],
            "summary": article["raw_summary"]
        },
        "enrichment": {
            "tags": tags,
            "audit_summary": article["audit_summary"],
            "classification_correct": bool(article["audit_classification_correct"]) if article["audit_classification_correct"] is not None else None
        },
        "version": "1.0"
    }

    # Generate robust filename: YYYYMMDDHASH.json (No symbols, purely alphanumeric)
    date_part = "00000000"
    if isinstance(article["pub_date"], datetime):
        date_part = article["pub_date"].strftime("%Y%m%d")
    elif isinstance(article["pub_date"], str) and len(article["pub_date"]) >= 10:
        # Try extract YYYY-MM-DD to YYYYMMDD
        raw_date = article["pub_date"][:10].replace("-", "").replace("/", "").replace(" ", "")
        if len(raw_date) == 8:
            date_part = raw_date
    
    # Filename uses date and first 12 chars of hash (robust, unique, no symbols)
    filename = f"{date_part}{url_hash[:12]}.json"
    file_path = hub_path / filename

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(hub_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Failed to save file: {str(e)}"}, status_code=500)

    return {"status": "success", "message": f"Saved to {filename}"}
