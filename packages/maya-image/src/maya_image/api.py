"""Public imagine API — JSON-first routes for gateway Alpine UI."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from maya_image.arena.service import get_arena_service
from maya_image.hub import ImagineJobEvent, hub
from maya_image.service import ImageJobService, get_image_service
from maya_image.templates import templates
from maya_image.types.image_job import ImageJobInput, ImageJobStatus, ImageMode
from maya_image.workflows import get_workflow, list_workflows

logger = structlog.get_logger()
router = APIRouter(tags=["imagine"])

# Bounded so a long-running gateway does not accumulate error strings unbounded.
_BATTLE_ERROR_CAP = 256
_battle_errors: dict[str, str] = {}

# Retain references to fire-and-forget background tasks so the event loop does
# not garbage-collect them mid-flight (see asyncio.create_task docs).
_background_tasks: set[asyncio.Task[Any]] = set()


def _record_battle_error(battle_id: str, error: str) -> None:
    if len(_battle_errors) >= _BATTLE_ERROR_CAP and battle_id not in _battle_errors:
        _battle_errors.pop(next(iter(_battle_errors)), None)
    _battle_errors[battle_id] = error


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _wants_json(request: Request) -> bool:
    if request.query_params.get("format") == "json":
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept


def _battle_view(battle, *, blind: bool = True) -> dict[str, Any]:
    svc = get_arena_service()
    artifacts = svc.get_artifacts(battle.id)
    by_slot = {a.slot: a for a in artifacts}

    def _url(art) -> str | None:
        if art is None:
            return None
        return art.url or art.local_path

    image_a = _url(by_slot.get("a"))
    image_b = _url(by_slot.get("b"))
    error = _battle_errors.get(battle.id)
    state = "generating"
    if battle.status == "completed":
        state = "resolved"
    elif image_a and image_b:
        state = "voting"
    elif error:
        state = "failed"

    ctx: dict[str, Any] = {
        "battle_id": battle.id,
        "prompt": battle.prompt,
        "state": state,
        "image_a": image_a,
        "image_b": image_b,
    }
    if error:
        ctx["error"] = error
    if state == "resolved" or not blind:
        cand_a = svc.get_candidate(battle.candidate_a_id)
        cand_b = svc.get_candidate(battle.candidate_b_id)
        ctx["model_a"] = cand_a.name if cand_a else "Model A"
        ctx["model_b"] = cand_b.name if cand_b else "Model B"
        ctx["rating_a"] = cand_a.rating if cand_a else None
        ctx["rating_b"] = cand_b.rating if cand_b else None
        if state == "resolved":
            ctx["winner"] = (
                "a"
                if battle.winner_id == battle.candidate_a_id
                else "b"
                if battle.winner_id == battle.candidate_b_id
                else "tie"
            )
    return ctx


def _recent_battle_views(limit: int = 8) -> list[dict[str, Any]]:
    svc = get_arena_service()
    return [_battle_view(b) for b in svc.get_battles(modality="image", limit=limit)]


def _default_workflow_id() -> str:
    workflows = list_workflows(category="t2i")
    if workflows:
        return workflows[0].id
    return "z-image-turbo-t2i"


def _battle_view_by_id(battle_id: str) -> dict[str, Any] | None:
    battle = get_arena_service().get_battle(battle_id)
    return _battle_view(battle) if battle else None


async def _run_battle_generation(
    service: ImageJobService,
    battle_id: str,
    job_ids: dict[str, str],
    candidate_ids: dict[str, str],
) -> None:
    logger.info("imagine_battle_finalize_start", battle_id=battle_id)
    try:
        await service.finalize_arena_jobs(battle_id, job_ids, candidate_ids)
        _battle_errors.pop(battle_id, None)
        logger.info("imagine_battle_finalize_ok", battle_id=battle_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("imagine_battle_finalize_failed", battle_id=battle_id, error=str(exc))
        _record_battle_error(battle_id, str(exc))
    ctx = await asyncio.to_thread(_battle_view_by_id, battle_id)
    if ctx:
        hub.upsert_battle(ctx)


@router.get("/gateway/imagine", response_class=HTMLResponse)
async def imagine_page(request: Request) -> HTMLResponse:
    """Forge-style arena composer — Alpine + static gateway assets."""
    battles = _recent_battle_views(limit=8)
    default_workflow_id = _default_workflow_id()
    bootstrap = {
        "battles": battles,
        "default_workflow_id": default_workflow_id,
        "sse_url": "/gateway/imagine/queue/stream",
    }
    return templates.TemplateResponse(
        request,
        "imagine/imagine_alpine.html",
        {
            "bootstrap_json": json.dumps(bootstrap),
            "default_workflow_id": default_workflow_id,
        },
    )


@router.get("/gateway/imagine/leaderboard")
async def imagine_leaderboard(request: Request):
    svc = get_arena_service()
    rows = await asyncio.to_thread(svc.get_leaderboard, 20, "image")
    candidates = [
        {
            "id": c.id,
            "name": c.name,
            "provider": c.provider,
            "model_key": c.model_key,
            "rating": c.rating,
            "wins": c.wins,
            "losses": c.losses,
            "draws": c.draws,
            "win_rate": c.win_rate,
        }
        for c in rows
    ]
    payload = {"candidates": candidates, "total": len(candidates)}
    return JSONResponse(payload)


@router.post("/gateway/imagine/generate")
async def imagine_generate(
    request: Request,
    prompt: str = Form(...),
    workflow_id: str = Form("z-image-turbo-t2i"),
    aspect: str = Form("1:1"),
    arena_mode: str = Form("default"),
):
    service = get_image_service()
    workflow = get_workflow(workflow_id)
    metadata = {
        "workflow_id": workflow.id,
        "aspect": aspect,
        "source": "gateway",
        "arena_mode": arena_mode,
    }
    job_input = ImageJobInput(
        prompt=prompt.strip(),
        mode=ImageMode.ARENA if arena_mode != "off" else ImageMode.GENERATE,
        user_id="anon",
        metadata=metadata,
    )

    if job_input.mode == ImageMode.ARENA:
        try:
            result = await service.submit_workflow_arena(job_input, source_workflow_id=workflow.id)
            battle = await asyncio.to_thread(get_arena_service().get_battle, result["battle_id"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("imagine_arena_submit_failed", prompt=prompt[:120], error=str(exc))
            return JSONResponse({"type": "error", "error": str(exc)}, status_code=502)
        _spawn_background(
            _run_battle_generation(
                service,
                result["battle_id"],
                result["job_ids"],
                result["candidate_ids"],
            )
        )
        ctx = _battle_view(battle)
        hub.upsert_battle(ctx)
        return JSONResponse({"type": "battle", "battle": ctx})

    try:
        job = await service.submit(workflow.provider_key or "comfyui:graph", job_input)
    except Exception as exc:  # noqa: BLE001
        logger.warning("imagine_generate_failed", prompt=prompt[:120], error=str(exc))
        evt = ImagineJobEvent(
            job_id=f"failed-{uuid.uuid4().hex}",
            status="failed",
            prompt=prompt,
            error=str(exc),
        )
        hub.upsert(evt)
        return JSONResponse({"type": "job", "job": evt.to_dict()}, status_code=502)

    hub.upsert(ImagineJobEvent(job_id=job.id, status=job.status.value, prompt=prompt))
    return JSONResponse({"type": "job", "job": {"job_id": job.id, "status": job.status.value}})


@router.get("/gateway/imagine/battle/{battle_id}")
async def imagine_battle(request: Request, battle_id: str):
    ctx = await asyncio.to_thread(_battle_view_by_id, battle_id)
    if ctx is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"battle": ctx})


@router.post("/gateway/imagine/vote")
async def imagine_vote(
    battle_id: str = Form(...),
    choice: str = Form(...),
):
    if choice not in {"a", "b"}:
        return JSONResponse({"error": "choice must be 'a' or 'b'"}, status_code=400)
    svc = get_arena_service()
    voter_id = "anon"

    def _vote_and_resolve() -> dict[str, Any] | None:
        try:
            svc.vote(battle_id, voter_id, "anon", choice)
            svc.complete_battle(battle_id)
        except ValueError as exc:
            logger.info("imagine_vote_noop", battle_id=battle_id, reason=str(exc))
        return _battle_view_by_id(battle_id)

    ctx = await asyncio.to_thread(_vote_and_resolve)
    if ctx is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    hub.upsert_battle(ctx)
    return JSONResponse({"type": "battle", "battle": ctx})


@router.get("/gateway/imagine/queue/stream")
async def imagine_queue_stream() -> StreamingResponse:
    async def event_generator() -> AsyncGenerator[str, None]:
        queue = hub.subscribe()
        try:
            yield f"data: {json.dumps({'status': 'ready'})}\n\n"
            while True:
                try:
                    _event, data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/gateway/imagine/workflows")
async def imagine_workflows():
    workflows = list_workflows(category="t2i")
    return JSONResponse(
        {
            "workflows": [
                {"id": w.id, "name": w.name, "provider_key": w.provider_key}
                for w in workflows
            ]
        }
    )
