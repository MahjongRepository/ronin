"""Persistence models for the data access layer."""

from datetime import datetime

from pydantic import BaseModel


class PlayedGame(BaseModel, frozen=True):
    """Record of a played game persisted to storage."""

    game_id: str
    started_at: datetime
    ended_at: datetime | None = None
    end_reason: str | None = None  # "completed" | "abandoned"
    player_ids: list[str]
