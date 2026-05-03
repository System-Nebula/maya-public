"""Discord Shim — HTTP glue between Discord gateway and Maya services.

This service receives Discord interaction payloads and forwards them
to the appropriate Maya gateway endpoint. It makes zero decisions.
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Discord Shim", version="0.1.0")

MAYA_GATEWAY_URL = os.getenv("MAYA_GATEWAY_URL", "http://localhost:8080")


@app.post("/discord/interaction")
async def interaction(req: Request):
    """Receive a Discord interaction and proxy it to the gateway."""
    payload = await req.json()

    # Stub: echo back the interaction type
    interaction_type = payload.get("type", 0)

    if interaction_type == 1:
        # PING
        return JSONResponse({"type": 1})

    # Everything else gets forwarded to Maya gateway
    # TODO: wire up httpx proxy to MAYA_GATEWAY_URL
    return JSONResponse(
        {
            "type": 4,
            "data": {
                "content": f"Shim received interaction type {interaction_type}. Gateway proxy not yet wired."
            },
        }
    )


def run() -> None:
    import uvicorn

    uvicorn.run(
        "discord_shim.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8081")),
    )
