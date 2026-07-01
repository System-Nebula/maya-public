"""Markdown → HTML rendering for the docs handbook.

Mintlify-style docs are authored as plain Markdown under ``docs/`` (Obsidian-
friendly, git-backed) and rendered server-side with Python-Markdown +
pymdown-extensions. Interactivity (global code-tab sync, copy buttons) is
layered on the client by ``/sdk/guide/guide.js`` — the markup stays static and
works without JavaScript.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import markdown

# docs/ lives at the repo root; override with MAYA_DOCS_ROOT in odd layouts.
DOCS_ROOT = Path(
    os.environ.get("MAYA_DOCS_ROOT", Path(__file__).resolve().parents[5] / "docs")
).resolve()

GITHUB_REPO = os.environ.get("DOCS_GITHUB_REPO", "System-Nebula/maya-public")
GITHUB_BRANCH = os.environ.get("DOCS_GITHUB_BRANCH", "main")

_MD_EXTENSIONS = [
    "meta",
    "toc",
    "tables",
    "admonition",
    "attr_list",
    "def_list",
    "sane_lists",
    "md_in_html",
    "pymdownx.superfences",
    "pymdownx.highlight",
    "pymdownx.inlinehilite",
    "pymdownx.tabbed",
    "pymdownx.tasklist",
    "pymdownx.betterem",
    "pymdownx.caret",
    "pymdownx.tilde",
]

_MD_CONFIG: dict[str, dict[str, Any]] = {
    "toc": {"permalink": True, "toc_depth": "2-3"},
    "pymdownx.tabbed": {"alternate_style": True},
    "pymdownx.highlight": {"anchor_linenums": False, "guess_lang": False},
    "pymdownx.tasklist": {"custom_checkbox": True},
}

_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)


class DocNotFound(Exception):
    """Requested docs page does not exist or escapes the docs root."""


@dataclass(frozen=True)
class RenderedDoc:
    slug: str
    title: str
    description: str
    html: str
    toc_html: str
    edit_url: str
    source_rel: str


@dataclass
class NavItem:
    title: str
    slug: str


@dataclass
class NavGroup:
    group: str
    items: list[NavItem] = field(default_factory=list)


def _resolve(slug: str) -> Path:
    """Map a URL slug to a Markdown file inside DOCS_ROOT (no traversal)."""
    slug = (slug or "index").strip("/")
    if not slug:
        slug = "index"
    candidate = (DOCS_ROOT / f"{slug}.md").resolve()
    # Guard against path traversal out of the docs root.
    if not str(candidate).startswith(str(DOCS_ROOT) + os.sep):
        raise DocNotFound(slug)
    if not candidate.is_file():
        raise DocNotFound(slug)
    return candidate


def _title_for(meta: dict[str, list[str]], source: str, slug: str) -> str:
    if meta.get("title"):
        return meta["title"][0]
    m = _H1_RE.search(source)
    if m:
        return m.group(1)
    return slug.rsplit("/", 1)[-1].replace("-", " ").title()


def render_doc(slug: str) -> RenderedDoc:
    path = _resolve(slug)
    source = path.read_text(encoding="utf-8")

    md = markdown.Markdown(extensions=_MD_EXTENSIONS, extension_configs=_MD_CONFIG)
    html = md.convert(source)
    meta = getattr(md, "Meta", {}) or {}
    toc_html = getattr(md, "toc", "") or ""

    rel = path.relative_to(DOCS_ROOT).as_posix()
    norm_slug = rel[:-3] if rel.endswith(".md") else rel
    title = _title_for(meta, source, norm_slug)
    description = meta["description"][0] if meta.get("description") else ""
    edit_url = f"https://github.com/{GITHUB_REPO}/edit/{GITHUB_BRANCH}/docs/{rel}"

    return RenderedDoc(
        slug=norm_slug,
        title=title,
        description=description,
        html=html,
        toc_html=toc_html,
        edit_url=edit_url,
        source_rel=f"docs/{rel}",
    )


@lru_cache(maxsize=1)
def _nav_path() -> Path:
    return DOCS_ROOT / "docs.json"


def load_nav() -> list[NavGroup]:
    """Read the Mintlify-style navigation manifest (docs/docs.json)."""
    nav_file = _nav_path()
    if not nav_file.is_file():
        return []
    data = json.loads(nav_file.read_text(encoding="utf-8"))
    groups: list[NavGroup] = []
    for grp in data.get("navigation", []):
        items = [NavItem(title=p["title"], slug=p["slug"]) for p in grp.get("pages", [])]
        groups.append(NavGroup(group=grp.get("group", ""), items=items))
    return groups


def flat_slugs(nav: list[NavGroup]) -> list[NavItem]:
    return [item for group in nav for item in group.items]
