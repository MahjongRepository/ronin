"""
Pydantic models for game logic data structures.

Contains typed models for round results, bot actions, available actions,
meld callers, and player views that cross component boundaries.
"""

from pydantic import BaseModel, Field

from game.logic.enums import (
    AbortiveDrawType,
    BotType,
    KanType,
    MeldCallType,
    MeldViewType,
    PlayerAction,
    RoundResultType,
)


class SeatConfig(BaseModel):
    """Configuration for a single seat in a game."""

    name: str
    is_bot: bool
    bot_type: BotType | None = None


class DiscardActionData(BaseModel):
    """Data for discard action."""

    tile_id: int


class RiichiActionData(BaseModel):
    """Data for riichi declaration action."""

    tile_id: int


class RonActionData(BaseModel):
    """Data for ron call action."""

    tile_id: int
    from_seat: int


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


class HandResultInfo(BaseModel):
    """Hand value information for win results."""

    han: int
    fu: int
    yaku: list[str]


class TsumoResult(BaseModel):
    """Result of a tsumo (self-draw) win."""

    type: RoundResultType = RoundResultType.TSUMO
    winner_seat: int
    hand_result: HandResultInfo
    score_changes: dict[int, int]
    riichi_sticks_collected: int


class RonResult(BaseModel):
    """Result of a ron (discard) win."""

    type: RoundResultType = RoundResultType.RON
    winner_seat: int
    loser_seat: int
    hand_result: HandResultInfo
    score_changes: dict[int, int]
    riichi_sticks_collected: int


class DoubleRonWinner(BaseModel):
    """Per-winner data in a double ron result."""

    winner_seat: int
    hand_result: HandResultInfo
    riichi_sticks_collected: int


class DoubleRonResult(BaseModel):
    """Result of a double ron win."""

    type: RoundResultType = RoundResultType.DOUBLE_RON
    loser_seat: int
    winners: list[DoubleRonWinner]
    score_changes: dict[int, int]


class ExhaustiveDrawResult(BaseModel):
    """Result of an exhaustive draw (wall empty)."""

    type: RoundResultType = RoundResultType.EXHAUSTIVE_DRAW
    tempai_seats: list[int]
    noten_seats: list[int]
    score_changes: dict[int, int]


class AbortiveDrawResult(BaseModel):
    """Result of an abortive draw."""

    type: RoundResultType = RoundResultType.ABORTIVE_DRAW
    reason: AbortiveDrawType
    score_changes: dict[int, int] = Field(default_factory=dict)
    seat: int | None = None


class PlayerStanding(BaseModel):
    """Player standing in final game results."""

    seat: int
    name: str
    score: int
    is_bot: bool


class GameEndResult(BaseModel):
    """Result of game finalization."""

    type: RoundResultType = RoundResultType.GAME_END
    winner_seat: int
    standings: list[PlayerStanding]


class MeldCaller(BaseModel):
    """Information about a player who can call a meld on a discarded tile."""

    seat: int
    call_type: MeldCallType
    tile_34: int
    priority: int
    options: list[tuple[int, int]] | None = None


class BotAction(BaseModel):
    """Bot's chosen action during their turn."""

    action: PlayerAction
    tile_id: int | None = None


class AvailableActionItem(BaseModel):
    """An available action for a player during their turn."""

    action: PlayerAction
    tiles: list[int] | None = None


class TileView(BaseModel):
    """Tile display information."""

    tile: str
    tile_id: int


class DiscardView(BaseModel):
    """Discard display information."""

    tile: str
    tile_id: int
    is_tsumogiri: bool
    is_riichi_discard: bool


class MeldView(BaseModel):
    """Meld display information."""

    type: MeldViewType
    tiles: list[str]
    tile_ids: list[int]
    opened: bool
    from_who: int | None


class PlayerView(BaseModel):
    """Player-visible information about another player."""

    seat: int
    name: str
    is_bot: bool
    score: int
    is_riichi: bool
    discards: list[DiscardView]
    melds: list[MeldView]
    tile_count: int
    tiles: list[int] | None = None
    hand: str | None = None


class GameView(BaseModel):
    """Complete game view for a specific player."""

    seat: int
    round_wind: str
    round_number: int
    dealer_seat: int
    current_player_seat: int
    wall_count: int
    dora_indicators: list[TileView]
    honba_sticks: int
    riichi_sticks: int
    players: list[PlayerView]
    phase: str
    game_phase: str


# discriminated union for all round results
RoundResult = TsumoResult | RonResult | DoubleRonResult | ExhaustiveDrawResult | AbortiveDrawResult
