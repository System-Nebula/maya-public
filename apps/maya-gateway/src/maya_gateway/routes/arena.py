"""Arena battle endpoints."""

from fastapi import APIRouter, HTTPException
from maya_contracts import (
    AddCandidateRequest,
    BattleResponse,
    CandidateResponse,
    CreateBattleRequest,
    LeaderboardResponse,
    StatsResponse,
    VoteRequest,
)

router = APIRouter(prefix="/api/arena", tags=["arena"])

# In-memory stub until db persistence is wired
_CANDIDATES: dict[str, dict] = {}
_BATTLES: dict[str, dict] = {}


@router.post("/candidates", response_model=CandidateResponse)
async def add_candidate(req: AddCandidateRequest):
    import uuid

    cid = str(uuid.uuid4())
    candidate = {
        "id": cid,
        "name": req.name,
        "provider": req.provider,
        "voice_id": req.voice_id,
        "rating": 1200,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "total_battles": 0,
        "win_rate": 0.0,
        "description": req.description,
        "is_active": True,
    }
    _CANDIDATES[cid] = candidate
    return CandidateResponse(**candidate)


@router.get("/candidates", response_model=LeaderboardResponse)
async def list_candidates():
    items = sorted(
        [CandidateResponse(**c) for c in _CANDIDATES.values()],
        key=lambda c: c.rating,
        reverse=True,
    )
    return LeaderboardResponse(candidates=items, total=len(items))


@router.post("/battles", response_model=BattleResponse)
async def create_battle(req: CreateBattleRequest):
    import uuid
    from datetime import datetime, timezone

    if req.candidate_a_id not in _CANDIDATES:
        raise HTTPException(status_code=404, detail="candidate_a not found")
    if req.candidate_b_id not in _CANDIDATES:
        raise HTTPException(status_code=404, detail="candidate_b not found")

    bid = str(uuid.uuid4())
    battle = {
        "id": bid,
        "candidate_a_id": req.candidate_a_id,
        "candidate_b_id": req.candidate_b_id,
        "prompt": req.prompt,
        "winner_id": None,
        "status": "open",
        "votes_a": 0,
        "votes_b": 0,
        "votes_tie": 0,
        "total_votes": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    _BATTLES[bid] = battle
    return BattleResponse(**battle)


@router.post("/battles/{battle_id}/vote", response_model=BattleResponse)
async def vote(battle_id: str, req: VoteRequest):
    from arena_core import ELOCalculator

    battle = _BATTLES.get(battle_id)
    if not battle:
        raise HTTPException(status_code=404, detail="battle not found")
    if battle["status"] != "open":
        raise HTTPException(status_code=400, detail="battle is closed")

    if req.choice == "a":
        battle["votes_a"] += 1
    elif req.choice == "b":
        battle["votes_b"] += 1
    elif req.choice == "tie":
        battle["votes_tie"] += 1
    else:
        raise HTTPException(status_code=400, detail="choice must be a, b, or tie")

    battle["total_votes"] += 1

    # Auto-close at 10 votes for demo
    if battle["total_votes"] >= 10:
        a = _CANDIDATES[battle["candidate_a_id"]]
        b = _CANDIDATES[battle["candidate_b_id"]]

        if battle["votes_a"] > battle["votes_b"]:
            winner = "a"
        elif battle["votes_b"] > battle["votes_a"]:
            winner = "b"
        else:
            winner = "tie"

        result = ELOCalculator.calculate_from_battle(
            a["rating"], b["rating"], winner, is_tie=(winner == "tie")
        )

        a["rating"] = result[0][0]
        b["rating"] = result[1][0]

        if winner == "a":
            a["wins"] += 1
            b["losses"] += 1
            battle["winner_id"] = a["id"]
        elif winner == "b":
            b["wins"] += 1
            a["losses"] += 1
            battle["winner_id"] = b["id"]
        else:
            a["draws"] += 1
            b["draws"] += 1

        a["total_battles"] += 1
        b["total_battles"] += 1
        a["win_rate"] = a["wins"] / max(a["total_battles"], 1)
        b["win_rate"] = b["wins"] / max(b["total_battles"], 1)
        battle["status"] = "completed"

    return BattleResponse(**battle)


@router.get("/stats", response_model=StatsResponse)
async def stats():
    return StatsResponse(
        total_candidates=len(_CANDIDATES),
        total_battles=len(_BATTLES),
        total_votes=sum(b["total_votes"] for b in _BATTLES.values()),
    )
