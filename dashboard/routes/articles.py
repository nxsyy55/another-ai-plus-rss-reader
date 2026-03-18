from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from aiNewReader.db import get_db, get_article_tags, init_db

router = APIRouter()
templates = Jinja2Templates(directory="templates/dashboard")


@router.get("/", response_class=HTMLResponse)
async def articles_page(
    request: Request,
    q: str = Query(default=""),
    language: str = Query(default=""),
    tag: str = Query(default=""),
    page: int = Query(default=1),
):
    init_db()
    limit = 20
    offset = (page - 1) * limit

    if q:
        from aiNewReader.rag.query import search as rag_search
        results = await rag_search(q, limit=limit, language=language or None, tag=tag or None)
        articles = results
        total = len(results)
    else:
        with get_db() as conn:
            where = "WHERE dedup_status='original'"
            params: list = []
            if language:
                where += " AND language=?"
                params.append(language)
            rows = conn.execute(
                f"SELECT * FROM articles {where} ORDER BY pub_date DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            total_row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM articles {where}", params
            ).fetchone()
            total = total_row["cnt"] if total_row else 0
            articles = []
            for row in rows:
                art = dict(row)
                tags = get_article_tags(conn, art["id"])
                art["tags"] = [{"tag": t["tag"], "confidence": t["confidence"]} for t in tags]
                articles.append(art)

    return templates.TemplateResponse("articles.html", {
        "request": request,
        "articles": articles,
        "q": q,
        "language": language,
        "tag": tag,
        "page": page,
        "total": total,
        "has_next": offset + limit < total,
        "has_prev": page > 1,
    })


@router.post("/feedback")
async def record_feedback(url: str = Form(...), signal: int = Form(...)):
    from aiNewReader.feedback import record_feedback as _fb
    await _fb(url, signal)
    return RedirectResponse(url="/articles/", status_code=303)
