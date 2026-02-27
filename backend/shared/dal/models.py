"""Persistence models for the data access layer."""

from datetime import datetime

from pydantic import BaseModel, Field


class PlayedGameStanding(BaseModel, frozen=True):
    """Per-player info, populated at game start and enriched with scores at game end."""

    name: str  # player name (human or AI)
    seat: int
    user_id: str = ""  # user UUID (empty for AI players)
    score: int | None = None  # raw score at game end (e.g. 35000); None while in progress
    final_score: int | None = None  # uma/oka-adjusted score (e.g. +30); None while in progress


class PlayedGame(BaseModel, frozen=True):
    """Record of a played game persisted to storage."""

    game_id: str
    started_at: datetime
    ended_at: datetime | None = None
    end_reason: str | None = None  # "completed" | "abandoned"
    game_type: str = ""  # "hanchan" | "tonpusen" (from GameSettings.game_type)
    num_rounds_played: int | None = None  # total rounds played (only set at game end)
    # at start: seat order with names/seats/user_ids; at end: placement order with scores
    standings: list[PlayedGameStanding] = Field(default_factory=list)
