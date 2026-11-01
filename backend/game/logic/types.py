from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_serializer

from game.logic.enums import (
    AbortiveDrawType,
    AIPlayerType,
    CallType,
    HandLimit,
    KanType,
    MeldCallType,
    PaoShare,
    PlayerAction,
    RoundResultType,
    WindName,
    WireCallType,
    WireGameType,
    WireMeldCallType,
    WirePlayerAction,
    WireWind,
)
from game.logic.settings import WIRE_SCORE_DIVISOR, GameType


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


def _game_type_to_wire(v: GameType) -> int:
    return WireGameType[v.name]


WireScore = Annotated[int, PlainSerializer(_score_to_wire)]
WireScoreMap = Annotated[dict[int, int], PlainSerializer(_score_map_to_wire)]
WireWindField = Annotated[WindName, PlainSerializer(_wind_to_wire)]
WireCallTypeField = Annotated[CallType, PlainSerializer(_call_type_to_wire)]
WireMeldCallTypeField = Annotated[MeldCallType, PlainSerializer(_meld_call_type_to_wire)]
WirePlayerActionField = Annotated[PlayerAction, PlainSerializer(_player_action_to_wire)]
WireGameTypeField = Annotated[GameType, PlainSerializer(_game_type_to_wire)]


class SeatConfig(BaseModel):
    """
    Configuration for a single seat in a game.
    """

    name: str
    ai_player_type: AIPlayerType | None = None


class GamePlayerInfo(BaseModel):
    """
    Player identity information sent at game start.
    """

    seat: int = Field(serialization_alias="s")
    name: str = Field(serialization_alias="nm")
    is_ai_player: bool = Field(serialization_alias="ai")

    @field_serializer("is_ai_player")
    @classmethod
    def _serialize_ai_as_int(cls, v: object) -> int:
        return int(bool(v))


class DiscardActionData(BaseModel):
    """
    Data for discard action.
    """

    tile_id: int


class RiichiActionData(BaseModel):
    """
    Data for riichi declaration action.
    """

    tile_id: int


class PonActionData(BaseModel):
    """
    Data for pon call action.
    """

    tile_id: int


class ChiActionData(BaseModel):
    """
    Data for chi call action.
    """

    tile_id: int
    sequence_tiles: tuple[int, int]


class KanActionData(BaseModel):
    """
    Data for kan call action.
    """

    tile_id: int
    kan_type: KanType = KanType.OPEN


class YakuInfo(BaseModel):
    """
    Per-yaku breakdown with han value, library yaku ID and how many yakuman the yaku counts as.

    yakuman_count is 0 for an ordinary yaku, 1 for a yakuman and 2 for a double yakuman, so a client tells a yakuman
    hand from a kazoe yakuman (13 han of ordinary yaku) and names a double yakuman without keeping its own list of the
    library's yakuman ids or its han per yakuman.
    """

    yaku_id: int = Field(serialization_alias="yi")
    han: int
    yakuman_count: int = Field(default=0, serialization_alias="ym")


class HandResultInfo(BaseModel):
    """
    Hand value information for win results.

    points is the hand's value without honba or riichi sticks, which pao does not change: the ron payment, or every
    tsumo payment together. limit is the limit the hand was paid at, and yakuman_count how many yakuman a yakuman or
    kazoe yakuman limit counts (None below them).
    """

    han: int
    fu: int
    yaku: list[YakuInfo] = Field(serialization_alias="yk")
    points: WireScore = Field(serialization_alias="pt")
    limit: HandLimit = Field(serialization_alias="lm")
    yakuman_count: int | None = Field(default=None, serialization_alias="yc")


class PaoLiability(BaseModel):
    """
    What the seat liable (pao) for a winner's yakuman pays: the pao yakuman of the hand it covers (yaku_ids), all or
    half of their value (share), and whether it also pays the winner's honba bonus.

    It names at least one pao yakuman, since a client rejects an empty list.
    """

    yaku_ids: list[int] = Field(min_length=1, serialization_alias="yk")
    share: PaoShare = Field(serialization_alias="sh")
    pays_honba: bool = Field(serialization_alias="hb")


class TsumoResult(BaseModel):
    """
    Result of a tsumo (self-draw) win.

    honba_bonus is the honba bonus the winner collected, every payer's together. pao_seat is the seat liable for the
    winner's yakuman and pao what it pays, both None without one.
    """

    type: RoundResultType = RoundResultType.TSUMO
    winner_seat: int = Field(serialization_alias="ws")
    hand_result: HandResultInfo = Field(serialization_alias="hr")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")
    riichi_sticks_collected: int = Field(serialization_alias="rc")
    closed_tiles: list[int] = Field(serialization_alias="ct")
    melds: list[int] = Field(serialization_alias="ml")
    win_tile: int = Field(serialization_alias="wt")
    honba_bonus: WireScore = Field(serialization_alias="hb")
    pao_seat: int | None = Field(default=None, serialization_alias="ps")
    pao: PaoLiability | None = Field(default=None, serialization_alias="pl")
    ura_dora_indicators: list[int] | None = Field(default=None, serialization_alias="ud")


class RobbedKan(BaseModel):
    """
    A kan robbed by chankan, as its declarer declared it: an added kan, or a closed kan robbed by kokushi musou.

    A robbed kan never completes, so no meld event records it; the result of the ron that robbed it carries it instead.
    """

    seat: int = Field(serialization_alias="s")
    tile_id: int = Field(serialization_alias="ti")
    kan_type: KanType = Field(serialization_alias="kty")


class RonResult(BaseModel):
    """
    Result of a ron (discard) win.

    robbed_kan is the kan the ron robbed, for a chankan; None for a ron on a discard. head_bumped_seats are the seats
    that also declared ron but lost it to head bump, in caller order; None when no declaration was bumped. honba_bonus
    is the honba bonus the winner collected; pao_seat is the seat liable for the winner's yakuman and pao what it pays,
    both None without one.
    """

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
    honba_bonus: WireScore = Field(serialization_alias="hb")
    pao_seat: int | None = Field(default=None, serialization_alias="ps")
    pao: PaoLiability | None = Field(default=None, serialization_alias="pl")
    ura_dora_indicators: list[int] | None = Field(default=None, serialization_alias="ud")
    robbed_kan: RobbedKan | None = Field(default=None, serialization_alias="rk")
    head_bumped_seats: list[int] | None = Field(default=None, serialization_alias="hbs")


class DoubleRonWinner(BaseModel):
    """
    Per-winner data in a double ron result.

    score_changes is this winner's own payments alone (the loser's, a pao seat's, the winner's honba and any riichi
    sticks), so the winners' maps sum to the result's score_changes. honba_bonus, pao_seat and pao are this winner's, as
    on a single ron.
    """

    winner_seat: int = Field(serialization_alias="ws")
    hand_result: HandResultInfo = Field(serialization_alias="hr")
    score_changes: WireScoreMap = Field(serialization_alias="sch")
    riichi_sticks_collected: int = Field(serialization_alias="rc")
    closed_tiles: list[int] = Field(serialization_alias="ct")
    melds: list[int] = Field(serialization_alias="ml")
    honba_bonus: WireScore = Field(serialization_alias="hb")
    pao_seat: int | None = Field(default=None, serialization_alias="ps")
    pao: PaoLiability | None = Field(default=None, serialization_alias="pl")
    ura_dora_indicators: list[int] | None = Field(default=None, serialization_alias="ud")


class DoubleRonResult(BaseModel):
    """
    Result of a double ron win.

    robbed_kan is the kan the rons robbed, for a chankan; None for rons on a discard. head_bumped_seats are the seats
    that also declared ron but lost it to head bump, in caller order; None when no declaration was bumped.
    """

    type: RoundResultType = RoundResultType.DOUBLE_RON
    loser_seat: int = Field(serialization_alias="ls")
    winning_tile: int = Field(serialization_alias="wt")
    winners: list[DoubleRonWinner] = Field(serialization_alias="wn")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")
    robbed_kan: RobbedKan | None = Field(default=None, serialization_alias="rk")
    head_bumped_seats: list[int] | None = Field(default=None, serialization_alias="hbs")


class TenpaiHand(BaseModel):
    """
    Hand data for a tenpai player revealed at exhaustive draw.
    """

    seat: int = Field(serialization_alias="s")
    closed_tiles: list[int] = Field(serialization_alias="ct")
    melds: list[int] = Field(serialization_alias="ml")


class ExhaustiveDrawResult(BaseModel):
    """
    Result of an exhaustive draw (wall empty).
    """

    type: RoundResultType = RoundResultType.EXHAUSTIVE_DRAW
    tempai_seats: list[int] = Field(serialization_alias="ts")
    noten_seats: list[int] = Field(serialization_alias="ns")
    tenpai_hands: list[TenpaiHand] = Field(serialization_alias="th")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")


class AbortiveDrawResult(BaseModel):
    """
    Result of an abortive draw.

    seat is the seat that declared kyuushu kyuuhai; ron_seats are the seats that declared a triple ron, in caller order
    (counter-clockwise from the discarder), and robbed_kan the kan they robbed when the triple ron was a chankan. All
    stay None for every other draw.
    """

    type: RoundResultType = RoundResultType.ABORTIVE_DRAW
    reason: AbortiveDrawType = Field(serialization_alias="rn")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")
    seat: int | None = Field(default=None, serialization_alias="s")
    ron_seats: list[int] | None = Field(default=None, serialization_alias="rcl")
    robbed_kan: RobbedKan | None = Field(default=None, serialization_alias="rk")


class DiscardInfo(BaseModel):
    """
    A discard as it lies in its river: in the reconnect snapshot, and in a nagashi mangan's proof.
    """

    tile_id: int = Field(serialization_alias="ti")
    is_tsumogiri: bool = Field(default=False, serialization_alias="tg")
    is_riichi_discard: bool = Field(default=False, serialization_alias="rd")


class NagashiRiver(BaseModel):
    """
    The river of a seat that made nagashi mangan, every discard in it as it fell: the result's proof, so a client never
    shows it from its own table.
    """

    seat: int = Field(serialization_alias="s")
    discards: list[DiscardInfo] = Field(serialization_alias="dsc")


class NagashiManganResult(BaseModel):
    """
    Result of a nagashi mangan at exhaustive draw.

    rivers holds each qualifying seat's river, in the order of qualifying_seats.
    """

    type: RoundResultType = RoundResultType.NAGASHI_MANGAN
    qualifying_seats: list[int] = Field(serialization_alias="qs")
    rivers: list[NagashiRiver] = Field(serialization_alias="qr")
    tempai_seats: list[int] = Field(serialization_alias="ts")
    noten_seats: list[int] = Field(serialization_alias="ns")
    tenpai_hands: list[TenpaiHand] = Field(serialization_alias="th")
    scores: WireScoreMap = Field(serialization_alias="scs")
    score_changes: WireScoreMap = Field(serialization_alias="sch")


class PlayerStanding(BaseModel):
    """
    Player standing in final game results.
    """

    seat: int = Field(serialization_alias="s")
    score: WireScore = Field(serialization_alias="sc")
    final_score: int = Field(serialization_alias="fs")


class GameEndResult(BaseModel):
    """
    Result of game finalization.
    """

    type: RoundResultType = RoundResultType.GAME_END
    winner_seat: int
    standings: list[PlayerStanding]
    leftover_riichi_bonus: int
    leftover_riichi_sticks: int


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
    """
    Input data for ron call processing.

    robbed_kan is the kan the ron robs, for a chankan; head_bumped_seats the declarers head bump left out of
    ron_callers, if any.
    """

    model_config = ConfigDict(frozen=True)

    ron_callers: list[int] = Field(min_length=1)
    tile_id: int
    discarder_seat: int
    robbed_kan: RobbedKan | None = None
    head_bumped_seats: list[int] | None = None


class MeldCallInput(BaseModel):
    """
    Input data for meld call processing.
    """

    model_config = ConfigDict(frozen=True)

    caller_seat: int
    call_type: MeldCallType
    tile_id: int
    sequence_tiles: tuple[int, int] | None = None


class AIPlayerAction(BaseModel):
    """
    AI player's chosen action during their turn.
    """

    action: PlayerAction
    tile_id: int | None = None


class AvailableActionItem(BaseModel):
    """
    An available action for a player during their turn.
    """

    action: WirePlayerActionField = Field(serialization_alias="a")
    tiles: list[int] | None = Field(default=None, serialization_alias="tl")


class PlayerView(BaseModel):
    """
    Player-visible information about another player.
    """

    seat: int = Field(serialization_alias="s")
    score: WireScore = Field(serialization_alias="sc")


class PlayerReconnectState(BaseModel):
    """
    Per-player visible state in a reconnection snapshot.

    tile_count is the number of tiles in the player's closed hand (3n+2 while it holds its turn's draw), which other
    seats see face down but whose draws the snapshot does not replay.
    """

    seat: int = Field(serialization_alias="s")
    score: WireScore = Field(serialization_alias="sc")
    discards: list[DiscardInfo] = Field(serialization_alias="dsc")
    melds: list[int] = Field(serialization_alias="ml")
    is_riichi: bool = Field(serialization_alias="ri")
    tile_count: int = Field(serialization_alias="tc")


class RoundHistoryEntry(BaseModel):
    """
    A finished round as the final standings' ledger shows it: its wind, dealer and honba, and its outcome.

    round_in_wind, its number within the wind (from 1), stays off the wire: the reconnect snapshot's header reads it for
    a round that ended.

    result_type is the result's type, and abortive_reason is set only on an abortive draw. riichi_seats are the seats
    whose riichi stood, so their deposit counts against the round; winner_seats is empty on a draw and holds every
    winner of a double ron; loser_seat is set on a ron; pao_seats are the seats liable for a winner's yakuman (pao), in
    seat order and empty when none was; tenpai_seats only on a draw that judges tenpai (exhaustive or nagashi mangan).
    """

    model_config = ConfigDict(frozen=True)

    round_wind: WireWindField = Field(serialization_alias="w")
    round_in_wind: int = Field(exclude=True)
    dealer_seat: int = Field(serialization_alias="dl")
    honba_sticks: int = Field(serialization_alias="h")
    result_type: RoundResultType = Field(serialization_alias="rt")
    abortive_reason: AbortiveDrawType | None = Field(default=None, serialization_alias="rn")
    riichi_seats: tuple[int, ...] = Field(serialization_alias="rs")
    winner_seats: tuple[int, ...] = Field(serialization_alias="ws")
    loser_seat: int | None = Field(default=None, serialization_alias="ls")
    pao_seats: tuple[int, ...] = Field(serialization_alias="ps")
    tenpai_seats: tuple[int, ...] | None = Field(default=None, serialization_alias="ts")
    score_changes: WireScoreMap = Field(serialization_alias="sch")


# discriminated union for all round results
RoundResult = (
    TsumoResult | RonResult | DoubleRonResult | ExhaustiveDrawResult | AbortiveDrawResult | NagashiManganResult
)


class ReconnectionSnapshot(BaseModel):
    """
    Full game state snapshot sent to a reconnecting player.

    is_furiten is the furiten last reported to the reconnecting seat (FuritenTracker): the furiten event goes only to
    its seat and is not sent again, so the snapshot restores it. round_history lists every finished round in play order,
    the current one included once it has ended, so a reconnected client's standings cover the rounds it never saw.
    result is the round's result through its round-advance wait, None while the round is in play. During that wait
    the snapshot shows the round that ended: its dealer, wind, round number, number within the wind and honba with its
    tiles, beside the scores and riichi sticks the result left. A robbed kan is in no meld list, so the result's robbed
    kan is the one record of it for the reconnected table. latest_discard_seat is the seat whose discard is the round's
    latest, which lies last in its river; None (absent on the wire) before the round's first discard and once a meld
    claimed the latest one. riichi_stick_value is the game's, and first_dealer_seat the game's first dealer, as
    game_started carries them.
    """

    game_id: str = Field(serialization_alias="gid")
    players: list[GamePlayerInfo] = Field(serialization_alias="p")
    dealer_seat: int = Field(serialization_alias="dl")
    first_dealer_seat: int = Field(serialization_alias="fd")
    dealer_dice: tuple[tuple[int, int], tuple[int, int]] = Field(serialization_alias="dd")
    riichi_stick_value: WireScore = Field(serialization_alias="rsv")
    seat: int = Field(serialization_alias="s")
    round_wind: WireWindField = Field(serialization_alias="w")
    round_number: int = Field(serialization_alias="n")
    round_in_wind: int = Field(serialization_alias="rw")
    current_player_seat: int = Field(serialization_alias="cp")
    latest_discard_seat: int | None = Field(default=None, serialization_alias="ld")
    dora_indicators: list[int] = Field(serialization_alias="di")
    honba_sticks: int = Field(serialization_alias="h")
    riichi_sticks: int = Field(serialization_alias="r")
    my_tiles: list[int] = Field(serialization_alias="mt")
    dice: tuple[int, int] = Field(serialization_alias="dc")
    tiles_remaining: int = Field(serialization_alias="tr")
    player_states: list[PlayerReconnectState] = Field(serialization_alias="pst")
    is_furiten: bool = Field(serialization_alias="f")
    round_history: list[RoundHistoryEntry] = Field(serialization_alias="rh")
    result: RoundResult | None = Field(default=None, serialization_alias="re")
