"""
Pydantic models for game logic data structures.

Contains typed models for round results, AI player actions, available actions,
meld callers, and player views that cross component boundaries.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from game.logic.enums import (
    AbortiveDrawType,
    AIPlayerType,
    KanType,
    MeldCallType,
    MeldViewType,
    PlayerAction,
    RoundResultType,
    WindName,
)


class SeatConfig(BaseModel):
    """Configuration for a single seat in a game."""

    name: str
    ai_player_type: AIPlayerType | None = None


class GamePlayerInfo(BaseModel):
    """Player identity information sent at game start."""

    seat: int
    name: str
    is_ai_player: bool


class DiscardActionData(BaseModel):
    """Data for discard action."""

    tile_id: int


class RiichiActionData(BaseModel):
    """Data for riichi declaration action."""

    tile_id: int


class PonActionData(BaseModel):
    """Data for pon call action."""

    tile_id: int


class ChiActionData(BaseModel):
    """Data for chi call action."""

    tile_id: int
    sequence_tiles: tuple[int, int]


class KanActionData(BaseModel):
    """Data for kan call action."""

    tile_id: int
    kan_type: KanType = KanType.OPEN


class YakuInfo(BaseModel):
    """Per-yaku breakdown with han value and library yaku ID."""

    yaku_id: int
    han: int


class HandResultInfo(BaseModel):
    """Hand value information for win results."""

    han: int
    fu: int
    yaku: list[YakuInfo]


class TsumoResult(BaseModel):
    """Result of a tsumo (self-draw) win."""

    type: RoundResultType = RoundResultType.TSUMO
    winner_seat: int
    hand_result: HandResultInfo
    scores: dict[int, int]
    score_changes: dict[int, int]
    riichi_sticks_collected: int
    closed_tiles: list[int]
    melds: list[MeldView]
    win_tile: int
    pao_seat: int | None = None
    ura_dora_indicators: list[int] | None = None


class RonResult(BaseModel):
    """Result of a ron (discard) win."""

    type: RoundResultType = RoundResultType.RON
    winner_seat: int
    loser_seat: int
    winning_tile: int
    hand_result: HandResultInfo
    scores: dict[int, int]
    score_changes: dict[int, int]
    riichi_sticks_collected: int
    closed_tiles: list[int]
    melds: list[MeldView]
    pao_seat: int | None = None
    ura_dora_indicators: list[int] | None = None


class DoubleRonWinner(BaseModel):
    """Per-winner data in a double ron result."""

    winner_seat: int
    hand_result: HandResultInfo
    riichi_sticks_collected: int
    closed_tiles: list[int]
    melds: list[MeldView]
    pao_seat: int | None = None
    ura_dora_indicators: list[int] | None = None


class DoubleRonResult(BaseModel):
    """Result of a double ron win."""

    type: RoundResultType = RoundResultType.DOUBLE_RON
    loser_seat: int
    winning_tile: int
    winners: list[DoubleRonWinner]
    scores: dict[int, int]
    score_changes: dict[int, int]


class TenpaiHand(BaseModel):
    """Hand data for a tenpai player revealed at exhaustive draw."""

    seat: int
    closed_tiles: list[int]
    melds: list[MeldView]


class ExhaustiveDrawResult(BaseModel):
    """Result of an exhaustive draw (wall empty)."""

    type: RoundResultType = RoundResultType.EXHAUSTIVE_DRAW
    tempai_seats: list[int]
    noten_seats: list[int]
    tenpai_hands: list[TenpaiHand]
    scores: dict[int, int]
    score_changes: dict[int, int]


class AbortiveDrawResult(BaseModel):
    """Result of an abortive draw."""

    type: RoundResultType = RoundResultType.ABORTIVE_DRAW
    reason: AbortiveDrawType
    scores: dict[int, int]
    score_changes: dict[int, int] = Field(default_factory=dict)
    seat: int | None = None


class NagashiManganResult(BaseModel):
    """Result of a nagashi mangan at exhaustive draw."""

    type: RoundResultType = RoundResultType.NAGASHI_MANGAN
    qualifying_seats: list[int]
    tempai_seats: list[int]
    noten_seats: list[int]
    tenpai_hands: list[TenpaiHand]
    scores: dict[int, int]
    score_changes: dict[int, int]


class PlayerStanding(BaseModel):
    """Player standing in final game results."""

    seat: int
    name: str
    score: int  # raw game score (e.g. 42300)
    final_score: int  # uma/oka-adjusted score (e.g. 52)
    is_ai_player: bool


class GameEndResult(BaseModel):
    """Result of game finalization."""

    type: RoundResultType = RoundResultType.GAME_END
    winner_seat: int
    standings: list[PlayerStanding]


class MeldCaller(BaseModel):
    """
    Immutable meld caller information.

    Uses tuple instead of list for options to prevent nested mutation.
    """

    model_config = ConfigDict(frozen=True)

    seat: int
    call_type: MeldCallType
    options: tuple[tuple[int, int], ...] | None = None


class AIPlayerAction(BaseModel):
    """AI player's chosen action during their turn."""

    action: PlayerAction
    tile_id: int | None = None


class AvailableActionItem(BaseModel):
    """An available action for a player during their turn."""

    action: PlayerAction
    tiles: list[int] | None = None

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        """Omit tiles field when it is None."""
        d: dict[str, Any] = {"action": self.action}
        if self.tiles is not None:
            d["tiles"] = self.tiles
        return d


class MeldView(BaseModel):
    """Meld display information."""

    type: MeldViewType
    tile_ids: list[int]
    opened: bool
    from_who: int | None


class PlayerView(BaseModel):
    """Player-visible information about another player."""

    seat: int
    name: str
    is_ai_player: bool
    score: int


class GameView(BaseModel):
    """Complete game view for a specific player."""

    seat: int
    round_wind: WindName
    round_number: int
    dealer_seat: int
    current_player_seat: int
    dora_indicators: list[int]
    honba_sticks: int
    riichi_sticks: int
    my_tiles: list[int]
    players: list[PlayerView]
    dice: tuple[int, int] = (1, 1)


# discriminated union for all round results
RoundResult = (
    TsumoResult
    | RonResult
    | DoubleRonResult
    | ExhaustiveDrawResult
    | AbortiveDrawResult
    | NagashiManganResult
)
