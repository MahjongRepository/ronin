from datetime import datetime
from enum import StrEnum
from statistics import fmean
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class PlayedGameStanding(BaseModel, frozen=True):
    """
    Per-player info, populated at game start and enriched with scores at game end.
    """

    name: str  # player name (human or AI)
    seat: int
    user_id: str = ""  # user UUID (empty for AI players)
    score: int | None = None  # raw score at game end (e.g. 35000); None while in progress
    final_score: int | None = None
    """
    Uma/oka-adjusted score in tenths (e.g. +304 for +30.4); None while in progress.
    """


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


type GameTiming = tuple[GameEndReason | None, datetime, datetime | None]


def nearest_rank_percentile(sorted_values: Sequence[float], percent: int) -> float:
    """
    Return the nearest-rank percentile of ascending values: the ``ceil(percent / 100 * n)``-th smallest, at least the
    first.
    """
    rank = max(-(-percent * len(sorted_values) // 100), 1)
    return sorted_values[rank - 1]


class DurationStats(BaseModel, frozen=True):
    mean_seconds: float
    median_seconds: float
    p90_seconds: float


class GamesSummary(BaseModel, frozen=True):
    """
    Counts of a cohort of games by how each ended, a game with no end being unfinished, and the completed games'
    durations, None when the cohort has no completed game.
    """

    started: int
    completed: int
    abandoned: int
    error: int
    unfinished: int
    completed_durations: DurationStats | None

    @classmethod
    def from_timings(cls, timings: Iterable[GameTiming]) -> Self:
        """
        Summarize games given as (end reason, start, end); a game without an end never counts as completed.
        """
        started = 0
        unfinished = 0
        ended_by_reason: dict[GameEndReason, int] = dict.fromkeys(GameEndReason, 0)
        durations: list[float] = []
        for end_reason, started_at, ended_at in timings:
            started += 1
            if ended_at is None:
                unfinished += 1
                continue

            if end_reason is not None:
                ended_by_reason[end_reason] += 1

            if end_reason == GameEndReason.COMPLETED:
                durations.append((ended_at - started_at).total_seconds())

        durations.sort()
        completed_durations = None
        if durations:
            completed_durations = DurationStats(
                mean_seconds=fmean(durations),
                median_seconds=nearest_rank_percentile(durations, 50),
                p90_seconds=nearest_rank_percentile(durations, 90),
            )

        return cls(
            started=started,
            completed=ended_by_reason[GameEndReason.COMPLETED],
            abandoned=ended_by_reason[GameEndReason.ABANDONED],
            error=ended_by_reason[GameEndReason.ERROR],
            unfinished=unfinished,
            completed_durations=completed_durations,
        )


class AccountType(StrEnum):
    HUMAN = "human"
    BOT = "bot"


class Player(BaseModel, frozen=True):
    """
    Player account stored in the player repository.

    Humans carry a bcrypt `password_hash` and, once they issue an API token on the settings page, a SHA-256
    `api_key_hash`; bots carry the "!" sentinel as `password_hash` and always an `api_key_hash`.
    """

    user_id: str
    username: str
    password_hash: str
    account_type: AccountType = AccountType.HUMAN
    api_key_hash: str | None = None
    is_admin: bool = False

    @model_validator(mode="after")
    def _validate_account_fields(self) -> Self:
        if self.account_type == AccountType.HUMAN and not self.password_hash:
            raise ValueError("Human accounts must have a password hash")

        if self.account_type == AccountType.BOT and not self.api_key_hash:
            raise ValueError("Bot accounts must have an api_key_hash")

        return self


class AuthSession(BaseModel, frozen=True):
    """
    A lobby session stored in the session repository, keyed by the SHA-256 hash of its cookie token.

    The raw token lives only in the browser cookie. Times are epoch seconds.
    """

    token_hash: str
    user_id: str
    username: str
    is_guest: bool
    created_at: float
    expires_at: float


class Tournament(BaseModel, frozen=True):
    """
    A tournament stored in the tournament repository; its owner is the account that created it.

    `created_at` and `finished_at` are epoch seconds; `finished_at` is None until the owner finishes it.
    """

    id: str
    name: str
    owner_user_id: str
    created_at: float
    finished_at: float | None = None


class TournamentGameCounts(BaseModel, frozen=True):
    """
    How many of a tournament's games are still playing and how many have finished.
    """

    playing: int
    finished: int


class TournamentGame(BaseModel, frozen=True):
    """
    A game started for a tournament: its players East to North, and its finish once the game has one.

    `created_at` and `ended_at` are epoch seconds; `result` holds the final standings.
    """

    game_id: str
    tournament_id: str
    players: list[str]
    created_at: float
    ended_at: float | None = None
    end_reason: GameEndReason | None = None
    result: list[PlayedGameStanding] | None = None
