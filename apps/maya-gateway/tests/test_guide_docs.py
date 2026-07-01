"""Tests for the docs handbook (render service + routes)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from maya_gateway.main import app
from maya_gateway.services.docs_render import (
    DocNotFound,
    flat_slugs,
    load_nav,
    render_doc,
)

client = TestClient(app)


def test_nav_loads():
    nav = load_nav()
    assert nav, "docs.json navigation should load"
    groups = {g.group for g in nav}
    assert "Control Panel" in groups


def test_every_nav_page_renders():
    for item in flat_slugs(load_nav()):
        doc = render_doc(item.slug)
        assert doc.html
        assert doc.title
        assert doc.edit_url.startswith("https://github.com/")


def test_render_constructs():
    doc = render_doc("kitchen-sink")
    assert "tabbed-set" in doc.html  # polyglot tabs
    assert "admonition" in doc.html  # callouts
    assert "<table>" in doc.html


def test_traversal_blocked():
    for bad in ["../pyproject", "../../etc/passwd", "control-panel/../../secrets"]:
        try:
            render_doc(bad)
            raised = False
        except DocNotFound:
            raised = True
        assert raised, f"expected DocNotFound for {bad!r}"


def test_route_home_ok():
    r = client.get("/guide")
    assert r.status_code == 200
    assert "Maya Handbook" in r.text
    assert "/sdk/guide/guide.css" in r.text


def test_route_page_ok_and_edit_link():
    r = client.get("/guide/control-panel/detection-engine")
    assert r.status_code == 200
    assert "Detection Engine" in r.text
    assert "edit/main/docs/control-panel/detection-engine.md" in r.text


def test_route_404():
    r = client.get("/guide/nope/does-not-exist")
    assert r.status_code == 404
