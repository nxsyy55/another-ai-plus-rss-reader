from __future__ import annotations

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
import sqlite3
from typing import Any

from aiNewReader.db import get_db, init_db
from ..templates import templates

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def query_page(request: Request):
    return templates.TemplateResponse("query.html", {
        "request": request,
        "query": "",
        "results": None,
        "error": None,
        "columns": None
    })

@router.post("/", response_class=HTMLResponse)
async def execute_query(request: Request, sql: str = Form(...)):
    init_db()
    results = []
    columns = []
    error = None
    
    # Simple security check (optional, but good practice even for local tools)
    # If you want to allow DELETE/UPDATE, remove this check.
    # The user said "control panel", so maybe they DO want to run updates.
    # I'll allow everything but wrap in try-except.
    
    try:
        with get_db() as conn:
            # We use a raw cursor to get column names easily
            cur = conn.execute(sql)
            if cur.description:
                columns = [column[0] for column in cur.description]
                results = cur.fetchall()
            else:
                # For non-SELECT queries
                conn.commit()
                results = [{"message": f"Query executed successfully. Rows affected: {cur.rowcount}"}]
                columns = ["status"]
    except sqlite3.Error as e:
        error = str(e)
    except Exception as e:
        error = f"An unexpected error occurred: {str(e)}"

    template = "_query_results.html" if request.headers.get("HX-Request") else "query.html"
    
    return templates.TemplateResponse(template, {
        "request": request,
        "query": sql,
        "results": [dict(r) if hasattr(r, 'keys') else r for r in results],
        "columns": columns,
        "error": error
    })
