from __future__ import annotations

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aiNewReader.db import get_db, get_all_feeds, upsert_feed, init_db

router = APIRouter()
templates = Jinja2Templates(directory="templates/dashboard")


@router.get("/", response_class=HTMLResponse)
async def feeds_page(request: Request):
    init_db()
    with get_db() as conn:
        feeds = get_all_feeds(conn)
    return templates.TemplateResponse("feeds.html", {"request": request, "feeds": [dict(f) for f in feeds]})


@router.post("/add")
async def add_feed(request: Request, url: str = Form(...), name: str = Form("")):
    from fastapi.responses import RedirectResponse
    from aiNewReader.fetcher import save_feeds_to_yaml
    with get_db() as conn:
        upsert_feed(conn, url, name or url)
    save_feeds_to_yaml()
    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/remove")
async def remove_feed(url: str = Form(...)):
    from fastapi.responses import RedirectResponse
    from aiNewReader.fetcher import save_feeds_to_yaml
    from aiNewReader.db import delete_feed_by_url
    with get_db() as conn:
        delete_feed_by_url(conn, url)
    save_feeds_to_yaml()
    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/disable")
async def disable_feed(url: str = Form(...)):
    from fastapi.responses import RedirectResponse
    with get_db() as conn:
        conn.execute("UPDATE feeds SET enabled=0 WHERE url=?", (url,))
    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/enable")
async def enable_feed(url: str = Form(...)):
    from fastapi.responses import RedirectResponse
    with get_db() as conn:
        conn.execute("UPDATE feeds SET enabled=1 WHERE url=?", (url,))
    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/import-opml")
async def import_opml_upload(file: UploadFile = File(...)):
    from fastapi.responses import RedirectResponse
    from aiNewReader.fetcher import parse_opml, save_feeds_to_yaml
    init_db()
    content = (await file.read()).decode("utf-8", errors="replace")
    feeds = parse_opml(content)
    with get_db() as conn:
        for feed in feeds:
            upsert_feed(conn, feed["url"], feed["name"], True)
    save_feeds_to_yaml()
    return RedirectResponse(url=f"/feeds/?imported={len(feeds)}", status_code=303)


@router.get("/export-opml")
async def export_opml(filename: str = "feeds.opml"):
    from fastapi.responses import Response
    from aiNewReader.fetcher import generate_opml
    
    if not filename.endswith('.opml') and not filename.endswith('.xml'):
        filename += '.opml'
        
    with get_db() as conn:
        feeds = get_all_feeds(conn)
    feeds_list = [{"url": f["url"], "name": f["name"]} for f in feeds]
    opml_content = generate_opml(feeds_list)
    
    return Response(
        content=opml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
