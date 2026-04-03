from __future__ import annotations

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aiNewReader.db import get_db, get_all_feeds, upsert_feed, init_db
from ..templates import templates

router = APIRouter()


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
        feed = conn.execute("SELECT * FROM feeds WHERE url=?", (url,)).fetchone()
        # article_count is 0 for new feed
        feed_dict = dict(feed)
        feed_dict["article_count"] = 0
        
        # We need an index for the new row. 
        # A simple way is to use a timestamp or just a very large number if we don't know the count.
        # But better to just use the count of feeds.
        count = conn.execute("SELECT COUNT(*) as cnt FROM feeds").fetchone()["cnt"]
    save_feeds_to_yaml()
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("_feed_row.html", {
            "request": request, 
            "feed": feed_dict, 
            "index": count + 1000 # Avoid collision with existing loop indices
        }, headers={"X-Toast-Message": "Feed added successfully."})

    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/remove")
async def remove_feed(request: Request, url: str = Form(...)):
    from fastapi.responses import RedirectResponse, Response
    from aiNewReader.fetcher import save_feeds_to_yaml
    from aiNewReader.db import delete_feed_by_url
    with get_db() as conn:
        delete_feed_by_url(conn, url)
    save_feeds_to_yaml()
    
    if request.headers.get("HX-Request"):
        return Response(content="", headers={"X-Toast-Message": "Feed removed."})
        
    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/skip-llm")
async def skip_llm_route(request: Request, url: str = Form(...), index: int = Form(None)):
    from aiNewReader.fetcher import save_feeds_to_yaml
    with get_db() as conn:
        conn.execute("UPDATE feeds SET skip_llm=1 WHERE url=?", (url,))
        feed = conn.execute("SELECT * FROM feeds WHERE url=?", (url,)).fetchone()
        article_count = conn.execute("SELECT COUNT(*) as cnt FROM articles WHERE feed_id = ?", (feed["id"],)).fetchone()["cnt"]
    save_feeds_to_yaml()
    
    if request.headers.get("HX-Request") and index is not None:
        feed_dict = dict(feed)
        feed_dict["article_count"] = article_count
        return templates.TemplateResponse("_feed_row.html", {
            "request": request, 
            "feed": feed_dict, 
            "index": index
        }, headers={"X-Toast-Message": "LLM processing disabled for this feed."})
        
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/unskip-llm")
async def unskip_llm_route(request: Request, url: str = Form(...), index: int = Form(None)):
    from aiNewReader.fetcher import save_feeds_to_yaml
    with get_db() as conn:
        conn.execute("UPDATE feeds SET skip_llm=0 WHERE url=?", (url,))
        feed = conn.execute("SELECT * FROM feeds WHERE url=?", (url,)).fetchone()
        article_count = conn.execute("SELECT COUNT(*) as cnt FROM articles WHERE feed_id = ?", (feed["id"],)).fetchone()["cnt"]
    save_feeds_to_yaml()
    
    if request.headers.get("HX-Request") and index is not None:
        feed_dict = dict(feed)
        feed_dict["article_count"] = article_count
        return templates.TemplateResponse("_feed_row.html", {
            "request": request, 
            "feed": feed_dict, 
            "index": index
        }, headers={"X-Toast-Message": "LLM processing enabled for this feed."})
        
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/remove-batch")
async def remove_feeds_batch(request: Request):
    from fastapi.responses import RedirectResponse
    from aiNewReader.fetcher import save_feeds_to_yaml
    from aiNewReader.db import delete_feeds_batch
    
    form_data = await request.form()
    urls = form_data.getlist("urls")
    
    if urls:
        with get_db() as conn:
            delete_feeds_batch(conn, urls)
        save_feeds_to_yaml()
        
    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/disable")
async def disable_feed(request: Request, url: str = Form(...), index: int = Form(None)):
    with get_db() as conn:
        conn.execute("UPDATE feeds SET enabled=0 WHERE url=?", (url,))
        feed = conn.execute("SELECT * FROM feeds WHERE url=?", (url,)).fetchone()
        article_count = conn.execute("SELECT COUNT(*) as cnt FROM articles WHERE feed_id = ?", (feed["id"],)).fetchone()["cnt"]
    
    if request.headers.get("HX-Request") and index is not None:
        feed_dict = dict(feed)
        feed_dict["article_count"] = article_count
        return templates.TemplateResponse("_feed_row.html", {
            "request": request, 
            "feed": feed_dict, 
            "index": index
        }, headers={"X-Toast-Message": "Feed disabled."})
        
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/feeds/", status_code=303)


@router.post("/enable")
async def enable_feed(request: Request, url: str = Form(...), index: int = Form(None)):
    with get_db() as conn:
        conn.execute("UPDATE feeds SET enabled=1 WHERE url=?", (url,))
        feed = conn.execute("SELECT * FROM feeds WHERE url=?", (url,)).fetchone()
        article_count = conn.execute("SELECT COUNT(*) as cnt FROM articles WHERE feed_id = ?", (feed["id"],)).fetchone()["cnt"]

    if request.headers.get("HX-Request") and index is not None:
        feed_dict = dict(feed)
        feed_dict["article_count"] = article_count
        return templates.TemplateResponse("_feed_row.html", {
            "request": request, 
            "feed": feed_dict, 
            "index": index
        }, headers={"X-Toast-Message": "Feed enabled."})
        
    from fastapi.responses import RedirectResponse
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
