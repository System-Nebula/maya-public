"""Arena database models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from maya_db.base import Base, TimestampMixin, UUIDPrimaryKey


class Candidate(Base, UUIDPrimaryKey, TimestampMixin):
    """An arena candidate (TTS voice / image model / persona)."""

    __tablename__ = "arena_candidates"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rating: Mapped[int] = mapped_column(Integer, default=1200, nullable=False)
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    draws: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_battles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    battles_a: Mapped[list["Battle"]] = relationship(
        "Battle", foreign_keys="Battle.candidate_a_id", back_populates="candidate_a"
    )
    battles_b: Mapped[list["Battle"]] = relationship(
        "Battle", foreign_keys="Battle.candidate_b_id", back_populates="candidate_b"
    )


class Battle(Base, UUIDPrimaryKey, TimestampMixin):
    """An arena battle between two candidates."""

    __tablename__ = "arena_battles"

    candidate_a_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("arena_candidates.id"), nullable=False
    )
    candidate_b_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("arena_candidates.id"), nullable=False
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    winner_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)

    votes_a: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    votes_b: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    votes_tie: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    candidate_a: Mapped["Candidate"] = relationship(
        "Candidate", foreign_keys=[candidate_a_id], back_populates="battles_a"
    )
    candidate_b: Mapped["Candidate"] = relationship(
        "Candidate", foreign_keys=[candidate_b_id], back_populates="battles_b"
    )
