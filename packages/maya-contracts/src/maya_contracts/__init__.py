"""Maya public API contracts — Pydantic schemas shared across all services."""

from maya_contracts.common import (
    ErrorResponse,
    MediaSourceStatus,
    PaginatedResponse,
    StrictModel,
)
from maya_contracts.feed import (
    CommentResponse,
    MediaResponse,
    PostResponse,
    PresignedUrlResponse,
    SearchResult,
    SourceResponse,
    SubjectResponse,
)
from maya_contracts.arena import (
    AddCandidateRequest,
    BattleResponse,
    CandidateResponse,
    CreateBattleRequest,
    LeaderboardResponse,
    StatsResponse,
    VoteRequest,
)

__all__ = [
    "ErrorResponse",
    "MediaSourceStatus",
    "PaginatedResponse",
    "StrictModel",
    "CommentResponse",
    "MediaResponse",
    "PostResponse",
    "PresignedUrlResponse",
    "SearchResult",
    "SourceResponse",
    "SubjectResponse",
    "AddCandidateRequest",
    "BattleResponse",
    "CandidateResponse",
    "CreateBattleRequest",
    "LeaderboardResponse",
    "StatsResponse",
    "VoteRequest",
]
