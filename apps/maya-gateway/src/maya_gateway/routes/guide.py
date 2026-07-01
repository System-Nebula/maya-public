"""Docs handbook — server-rendered Markdown site (Mintlify-style).

Served under ``/guide`` (``/docs`` is the FastAPI Swagger UI). Pages are plain
Markdown under the repo ``docs/`` directory, rendered by
``services.docs_render`` and themed by ``templates/guide.html``.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from maya_gateway.services.docs_render import (
    DocNotFound,
    flat_slugs,
    load_nav,
    render_doc,
)

router = APIRouter(prefix="/guide", tags=["guide"])

_templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


def _context(request: Request, slug: str):
    nav = load_nav()
    doc = render_doc(slug)  # raises DocNotFound
    flat = flat_slugs(nav)
    prev_item = nxt_item = None
    for i, item in enumerate(flat):
        if item.slug == doc.slug:
            prev_item = flat[i - 1] if i > 0 else None
            nxt_item = flat[i + 1] if i + 1 < len(flat) else None
            break
    return {
        "doc": doc,
        "nav": nav,
        "current": doc.slug,
        "prev": prev_item,
        "next": nxt_item,
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def guide_home(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(request, "guide.html", _context(request, "index"))


@router.get("/{slug:path}", response_class=HTMLResponse)
async def guide_page(request: Request, slug: str) -> HTMLResponse:
    try:
        ctx = _context(request, slug)
    except DocNotFound:
        return HTMLResponse(
            "<h1>404 — page not found</h1>"
            '<p><a href="/guide">Back to the handbook</a></p>',
            status_code=404,
        )
    return _templates.TemplateResponse(request, "guide.html", ctx)
