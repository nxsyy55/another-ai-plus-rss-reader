from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from aiNewReader.db import get_db, init_db

router = APIRouter()
templates = Jinja2Templates(directory="templates/dashboard")


@router.get("/", response_class=HTMLResponse)
async def articles_page(
    request: Request,
    q: str = Query(default=""),
    page: int = Query(default=1),
):
    init_db()
    limit = 20
    offset = (page - 1) * limit

    with get_db() as conn:
        where = "WHERE dedup_status='original'"
        params: list = []
        if q:
            where += " AND (title LIKE ? OR markdown_content LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])

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
    start_page = max(1, page - 4)
    end_page = min(total_pages, page + 4)

    return templates.TemplateResponse("articles.html", {
        "request": request,
        "articles": articles,
        "q": q,
        "page": page,
        "total": total,
        "total_pages": total_pages,
        "start_page": start_page,
        "end_page": end_page,
        "has_next": offset + limit < total,
        "has_prev": page > 1,
    })
