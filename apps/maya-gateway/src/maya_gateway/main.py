"""Maya Public Gateway — FastAPI entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from obs_client import configure_logging

from maya_gateway.routes import arena, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("maya-gateway", log_level="INFO")
    yield


app = FastAPI(
    title="Maya Gateway",
    description="Public API surface for Arena, Feed, and Image services.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(health.router)
app.include_router(arena.router)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "maya_gateway.main:app",
        host="0.0.0.0",
        port=int(__import__("os").getenv("PORT", "8080")),
        reload=__import__("os").getenv("ENV", "production") == "development",
    )
