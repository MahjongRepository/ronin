"""
Pydantic models for game logic data structures.

Contains typed models for round results, AI player actions, available actions,
meld callers, and player views that cross component boundaries.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_serializer

from game.logic.enums import (
    AbortiveDrawType,
    AIPlayerType,
    CallType,
    KanType,
    MeldCallType,
    PlayerAction,
    RoundResultType,
    WindName,
    WireCallType,
    WireMeldCallType,
    WirePlayerAction,
    WireWind,
)

WIRE_SCORE_DIVISOR = 100  # Wire protocol divides scores by 100 (25000 → 250)


def _score_to_wire(v: int) -> int:
    return v // WIRE_SCORE_DIVISOR


def _score_map_to_wire(v: dict[int, int]) -> dict[int, int]:
    return {k: val // WIRE_SCORE_DIVISOR for k, val in v.items()}


def _wind_to_wire(v: WindName) -> int:
    return WireWind[v.name]


def _call_type_to_wire(v: CallType) -> int:
    return WireCallType[v.name]


def _meld_call_type_to_wire(v: MeldCallType) -> int:
    return WireMeldCallType[v.name]


def _player_action_to_wire(v: PlayerAction) -> int:
    return WirePlayerAction[v.name]


WireScore = Annotated[int, PlainSerializer(_score_to_wire)]
WireScoreMap = Annotated[dict[int, int], PlainSerializer(_score_map_to_wire)]
WireWindField = Annotated[WindName, PlainSerializer(_wind_to_wire)]
WireCallTypeField = Annotated[CallType, PlainSerializer(_call_type_to_wire)]
WireMeldCallTypeField = Annotated[MeldCallType, PlainSerializer(_meld_call_type_to_wire)]
WirePlayerActionField = Annotated[PlayerAction, PlainSerializer(_player_action_to_wire)]


class SeatConfig(BaseModel):
    """Configuration for a single seat in a game."""

    name: str
    ai_player_type: AIPlayerType | None = None


class GamePlayerInfo(BaseModel):
    """Player identity information sent at game start."""

    seat: int = Field(serialization_alias="s")
    name: str = Field(serialization_alias="nm")
    is_ai_player: bool = Field(serialization_alias="ai")

    @field_serializer("is_ai_player")
    @classmethod
    def _serialize_ai_as_int(cls, v: object) -> int:
        return int(bool(v))


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

    yaku_id: int = Field(serialization_alias="yi")
    han: int


class HandResultInfo(BaseModel):
    """Hand value information for win results."""

    han: int
    fu: int
    yaku: list[YakuInfo] = Field(serialization_alias="yk")


class TsumoResult(BaseModel):
    """Result of a tsumo (self-draw) win."""

    type: RoundResultType = RoundResultType.TSUMO
    winner_seat: int = Field(serialization_alias="ws")
    hand_result: HandResultInfo = Field(serialization_alias="hr")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")
    riichi_sticks_collected: int = Field(serialization_alias="rc")
    closed_tiles: list[int] = Field(serialization_alias="ct")
    melds: list[int] = Field(serialization_alias="ml")
    win_tile: int = Field(serialization_alias="wt")
    pao_seat: int | None = Field(default=None, serialization_alias="ps")
    ura_dora_indicators: list[int] | None = Field(default=None, serialization_alias="ud")


class RonResult(BaseModel):
    """Result of a ron (discard) win."""

    type: RoundResultType = RoundResultType.RON
    winner_seat: int = Field(serialization_alias="ws")
    loser_seat: int = Field(serialization_alias="ls")
    winning_tile: int = Field(serialization_alias="wt")
    hand_result: HandResultInfo = Field(serialization_alias="hr")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")
    riichi_sticks_collected: int = Field(serialization_alias="rc")
    closed_tiles: list[int] = Field(serialization_alias="ct")
    melds: list[int] = Field(serialization_alias="ml")
    pao_seat: int | None = Field(default=None, serialization_alias="ps")
    ura_dora_indicators: list[int] | None = Field(default=None, serialization_alias="ud")


class DoubleRonWinner(BaseModel):
    """Per-winner data in a double ron result."""

    winner_seat: int = Field(serialization_alias="ws")
    hand_result: HandResultInfo = Field(serialization_alias="hr")
    riichi_sticks_collected: int = Field(serialization_alias="rc")
    closed_tiles: list[int] = Field(serialization_alias="ct")
    melds: list[int] = Field(serialization_alias="ml")
    pao_seat: int | None = Field(default=None, serialization_alias="ps")
    ura_dora_indicators: list[int] | None = Field(default=None, serialization_alias="ud")


class DoubleRonResult(BaseModel):
    """Result of a double ron win."""

    type: RoundResultType = RoundResultType.DOUBLE_RON
    loser_seat: int = Field(serialization_alias="ls")
    winning_tile: int = Field(serialization_alias="wt")
    winners: list[DoubleRonWinner] = Field(serialization_alias="wn")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")


class TenpaiHand(BaseModel):
    """Hand data for a tenpai player revealed at exhaustive draw."""

    seat: int = Field(serialization_alias="s")
    closed_tiles: list[int] = Field(serialization_alias="ct")
    melds: list[int] = Field(serialization_alias="ml")


class ExhaustiveDrawResult(BaseModel):
    """Result of an exhaustive draw (wall empty)."""

    type: RoundResultType = RoundResultType.EXHAUSTIVE_DRAW
    tempai_seats: list[int] = Field(serialization_alias="ts")
    noten_seats: list[int] = Field(serialization_alias="ns")
    tenpai_hands: list[TenpaiHand] = Field(serialization_alias="th")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")


class AbortiveDrawResult(BaseModel):
    """Result of an abortive draw."""

    type: RoundResultType = RoundResultType.ABORTIVE_DRAW
    reason: AbortiveDrawType = Field(serialization_alias="rn")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(default_factory=dict, serialization_alias="sch")
    seat: int | None = Field(default=None, serialization_alias="s")


class NagashiManganResult(BaseModel):
    """Result of a nagashi mangan at exhaustive draw."""

    type: RoundResultType = RoundResultType.NAGASHI_MANGAN
    qualifying_seats: list[int] = Field(serialization_alias="qs")
    tempai_seats: list[int] = Field(serialization_alias="ts")
    noten_seats: list[int] = Field(serialization_alias="ns")
    tenpai_hands: list[TenpaiHand] = Field(serialization_alias="th")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")


class PlayerStanding(BaseModel):
    """Player standing in final game results."""

    seat: int = Field(serialization_alias="s")
    score: WireScore = Field(serialization_alias="sc")
    final_score: int = Field(serialization_alias="fs")


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

    seat: int = Field(serialization_alias="s")
    call_type: WireMeldCallTypeField = Field(serialization_alias="clt")
    options: tuple[tuple[int, int], ...] | None = Field(default=None, serialization_alias="opt")


class RonCallInput(BaseModel):
    """Input data for ron call processing."""

    model_config = ConfigDict(frozen=True)

    ron_callers: list[int]
    tile_id: int
    discarder_seat: int
    is_chankan: bool = False


class MeldCallInput(BaseModel):
    """Input data for meld call processing."""

    model_config = ConfigDict(frozen=True)

    caller_seat: int
    call_type: MeldCallType
    tile_id: int
    sequence_tiles: tuple[int, int] | None = None


class AIPlayerAction(BaseModel):
    """AI player's chosen action during their turn."""

    action: PlayerAction
    tile_id: int | None = None


class AvailableActionItem(BaseModel):
    """An available action for a player during their turn."""

    action: WirePlayerActionField = Field(serialization_alias="a")
    tiles: list[int] | None = Field(default=None, serialization_alias="tl")


class PlayerView(BaseModel):
    """Player-visible information about another player."""

    seat: int = Field(serialization_alias="s")
    score: WireScore = Field(serialization_alias="sc")


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


class DiscardInfo(BaseModel):
    """Discard tile information for reconnection snapshot."""

    tile_id: int = Field(serialization_alias="ti")
    is_tsumogiri: bool = Field(default=False, serialization_alias="tg")
    is_riichi_discard: bool = Field(default=False, serialization_alias="rd")


class PlayerReconnectState(BaseModel):
    """Per-player visible state in a reconnection snapshot."""

    seat: int = Field(serialization_alias="s")
    score: WireScore = Field(serialization_alias="sc")
    discards: list[DiscardInfo] = Field(serialization_alias="dsc")
    melds: list[int] = Field(serialization_alias="ml")
    is_riichi: bool = Field(serialization_alias="ri")


class ReconnectionSnapshot(BaseModel):
    """Full game state snapshot sent to a reconnecting player."""

    game_id: str = Field(serialization_alias="gid")
    players: list[GamePlayerInfo] = Field(serialization_alias="p")
    dealer_seat: int = Field(serialization_alias="dl")
    dealer_dice: tuple[tuple[int, int], tuple[int, int]] = Field(serialization_alias="dd")
    seat: int = Field(serialization_alias="s")
    round_wind: WireWindField = Field(serialization_alias="w")
    round_number: int = Field(serialization_alias="n")
    current_player_seat: int = Field(serialization_alias="cp")
    dora_indicators: list[int] = Field(serialization_alias="di")
    honba_sticks: int = Field(serialization_alias="h")
    riichi_sticks: int = Field(serialization_alias="r")
    my_tiles: list[int] = Field(serialization_alias="mt")
    dice: tuple[int, int] = Field(serialization_alias="dc")
    tiles_remaining: int = Field(serialization_alias="tr")
    player_states: list[PlayerReconnectState] = Field(serialization_alias="pst")


# discriminated union for all round results
RoundResult = (
    TsumoResult | RonResult | DoubleRonResult | ExhaustiveDrawResult | AbortiveDrawResult | NagashiManganResult
)
