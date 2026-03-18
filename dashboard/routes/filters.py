from __future__ import annotations

import json

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from aiNewReader.db import get_db, get_all_filter_rules, upsert_filter_rule, delete_filter_rule, init_db
from aiNewReader.filter import save_rules_to_yaml

router = APIRouter()
templates = Jinja2Templates(directory="templates/dashboard")


def _rules_to_list(rows) -> list[dict]:
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "action": r["action"],
            "tags": json.loads(r["tags"]),
            "keywords": json.loads(r["keywords"]),
            "priority": r["priority"],
            "enabled": bool(r["enabled"]),
        }
        for r in rows
    ]


@router.get("/", response_class=HTMLResponse)
async def filters_page(request: Request):
    init_db()
    with get_db() as conn:
        rows = get_all_filter_rules(conn)
    return templates.TemplateResponse("filters.html", {"request": request, "rules": _rules_to_list(rows)})


@router.post("/add")
async def add_rule(
    request: Request,
    name: str = Form(...),
    action: str = Form(...),
    tags: str = Form(""),
    keywords: str = Form(""),
    priority: int = Form(5),
):
    rule = {
        "name": name,
        "action": action,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
        "priority": priority,
        "enabled": True,
    }
    with get_db() as conn:
        upsert_filter_rule(conn, rule)
        rows = get_all_filter_rules(conn)
    save_rules_to_yaml(_rules_to_list(rows))
    return RedirectResponse(url="/filters/", status_code=303)


@router.post("/delete")
async def delete_rule(name: str = Form(...)):
    with get_db() as conn:
        delete_filter_rule(conn, name)
        rows = get_all_filter_rules(conn)
    save_rules_to_yaml(_rules_to_list(rows))
    return RedirectResponse(url="/filters/", status_code=303)


@router.post("/toggle")
async def toggle_rule(name: str = Form(...)):
    with get_db() as conn:
        row = conn.execute("SELECT enabled FROM filter_rules WHERE name=?", (name,)).fetchone()
        if row:
            conn.execute("UPDATE filter_rules SET enabled=? WHERE name=?", (not row["enabled"], name))
    return RedirectResponse(url="/filters/", status_code=303)
