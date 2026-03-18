from __future__ import annotations

import json

from fastapi import APIRouter, Request, Form, Query
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
async def filters_page(
    request: Request,
    error: str = Query(default=""),
    edit: str = Query(default=""),
):
    init_db()
    with get_db() as conn:
        rows = get_all_filter_rules(conn)
    rules = _rules_to_list(rows)
    edit_rule = next((r for r in rules if r["name"] == edit), None)
    return templates.TemplateResponse("filters.html", {
        "request": request,
        "rules": rules,
        "error": error,
        "edit_rule": edit_rule,
    })


@router.post("/add")
async def add_rule(
    name: str = Form(...),
    action: str = Form(...),
    tags: str = Form(""),
    keywords: str = Form(""),
    priority: int = Form(5),
):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM filter_rules WHERE name=?", (name,)).fetchone()
        if existing:
            return RedirectResponse(url=f"/filters/?error=Rule+%22{name}%22+already+exists.+Use+Edit+to+modify+it.", status_code=303)
        rule = {
            "name": name,
            "action": action,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
            "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
            "priority": priority,
            "enabled": True,
        }
        upsert_filter_rule(conn, rule)
        rows = get_all_filter_rules(conn)
    save_rules_to_yaml(_rules_to_list(rows))
    return RedirectResponse(url="/filters/", status_code=303)


@router.post("/update")
async def update_rule(
    original_name: str = Form(...),
    name: str = Form(...),
    action: str = Form(...),
    tags: str = Form(""),
    keywords: str = Form(""),
    priority: int = Form(5),
    enabled: str = Form("on"),
):
    with get_db() as conn:
        # If name changed, check new name doesn't conflict with another rule
        if name != original_name:
            conflict = conn.execute(
                "SELECT id FROM filter_rules WHERE name=? AND name!=?", (name, original_name)
            ).fetchone()
            if conflict:
                return RedirectResponse(
                    url=f"/filters/?error=Rule+%22{name}%22+already+exists.&edit={original_name}",
                    status_code=303,
                )
            # Rename: delete old, insert new
            conn.execute("DELETE FROM filter_rules WHERE name=?", (original_name,))

        rule = {
            "name": name,
            "action": action,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
            "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
            "priority": priority,
            "enabled": enabled == "on",
        }
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
        rows = get_all_filter_rules(conn)
    save_rules_to_yaml(_rules_to_list(rows))
    return RedirectResponse(url="/filters/", status_code=303)
