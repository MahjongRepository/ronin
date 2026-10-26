from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class PlayedGameStanding(BaseModel, frozen=True):
    """
    Per-player info, populated at game start and enriched with scores at game end.
    """

    name: str  # player name (human or AI)
    seat: int
    user_id: str = ""  # user UUID (empty for AI players)
    score: int | None = None  # raw score at game end (e.g. 35000); None while in progress
    final_score: int | None = None  # uma/oka-adjusted score (e.g. +30); None while in progress


class GameEndReason(StrEnum):
    """
    Why a played game ended: played to the end, abandoned, or failed on a server error.

    ABANDONED means no human connection remains, not that a player is at fault: the last connected human left a game
    still playing (a reload in a solo game, or a graceful stop closing the sockets), or the pending timeout found nobody
    connected (that game never started, so it records no finish).
    """

    COMPLETED = "completed"
    ABANDONED = "abandoned"
    ERROR = "error"


class PlayedGame(BaseModel, frozen=True):
    """
    Record of a played game persisted to storage.
    """

    game_id: str
    started_at: datetime
    ended_at: datetime | None = None
    end_reason: GameEndReason | None = None
    game_type: str = ""  # "hanchan" | "tonpusen" (from GameSettings.game_type)
    num_rounds_played: int | None = None  # total rounds played (only set at game end)
    # at start: seat order with names/seats/user_ids; at end: placement order with scores
    standings: list[PlayedGameStanding] = Field(default_factory=list)


class AccountType(StrEnum):
    HUMAN = "human"
    BOT = "bot"


class Player(BaseModel, frozen=True):
    """
    Player account stored in the player repository.

    Humans carry a bcrypt `password_hash`; bots carry the "!" sentinel there and a SHA-256 `api_key_hash`.
    """

    user_id: str
    username: str
    password_hash: str
    account_type: AccountType = AccountType.HUMAN
    api_key_hash: str | None = None

    @model_validator(mode="after")
    def _validate_account_fields(self) -> Self:
        if self.account_type == AccountType.HUMAN and not self.password_hash:
            raise ValueError("Human accounts must have a password hash")

        if self.account_type == AccountType.BOT and not self.api_key_hash:
            raise ValueError("Bot accounts must have an api_key_hash")

        return self
