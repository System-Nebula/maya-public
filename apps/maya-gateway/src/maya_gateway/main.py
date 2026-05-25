"""Maya Public Gateway — FastAPI entrypoint."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from obs_client import configure_logging

from maya_gateway.routes import arena, health, registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("maya-gateway", log_level="INFO")
    yield


app = FastAPI(
    title="Maya Gateway",
    description="Public API surface for Arena, Feed, Registry, and Image services.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# API routes (all prefixed /api/* except docs)
app.include_router(health.router)
app.include_router(arena.router)
app.include_router(registry.router)

# SPA fallback: serve the start-page for non-API paths
static_dir = Path(__file__).with_name("static").resolve()


@app.get("/")
async def root():
    return FileResponse(static_dir / "index.html")


@app.get("/{path:path}")
async def spa_catchall(path: str):
    # Never shadow API or docs routes
    if path.startswith(("api/", "docs", "redoc", "openapi.json")):
        raise HTTPException(status_code=404, detail="Not found")
    # Serve static file if it exists, otherwise fallback to index.html
    target = static_dir / path
    if target.exists() and target.is_file():
        return FileResponse(target)
    return FileResponse(static_dir / "index.html")


def run() -> None:
    import uvicorn

    uvicorn.run(
        "maya_gateway.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=os.getenv("ENV", "production") == "development",
    )
