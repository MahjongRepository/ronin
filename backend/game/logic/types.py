from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from game.logic.enums import (
    AbortiveDrawType,
    AIPlayerType,
    HandLimit,
    KanType,
    MeldCallType,
    PaoShare,
    PlayerAction,
    RoundResultType,
    WindName,
)
from game.logic.settings import GameType
from game.logic.tiles import NUM_TILES

_TileId = Annotated[int, Field(ge=0, lt=NUM_TILES, strict=True)]


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

    seat: int
    name: str
    is_ai_player: bool


class DiscardActionData(BaseModel):
    """
    Data for discard action.
    """

    tile_id: _TileId


class RiichiActionData(BaseModel):
    """
    Data for riichi declaration action.
    """

    tile_id: _TileId


class PonActionData(BaseModel):
    """
    Data for pon call action.
    """

    tile_id: _TileId


class ChiActionData(BaseModel):
    """
    Data for chi call action.
    """

    tile_id: _TileId
    sequence_tiles: tuple[_TileId, _TileId]


class KanActionData(BaseModel):
    """
    Data for kan call action.
    """

    tile_id: _TileId
    kan_type: KanType


class YakuInfo(BaseModel):
    """
    Per-yaku breakdown with han value, library yaku ID and how many yakuman the yaku counts as.

    yakuman_count is 0 for an ordinary yaku, 1 for a yakuman and 2 for a double yakuman, so a client tells a yakuman
    hand from a kazoe yakuman (13 han of ordinary yaku) and names a double yakuman without keeping its own list of the
    library's yakuman ids or its han per yakuman.
    """

    yaku_id: int
    han: int
    yakuman_count: int = 0


class HandResultInfo(BaseModel):
    """
    Hand value information for win results.

    points is the hand's value without honba or riichi sticks, which pao does not change: the ron payment, or every
    tsumo payment together. limit is the limit the hand was paid at, and yakuman_count how many yakuman a yakuman or
    kazoe yakuman limit counts (None below them).
    """

    han: int
    fu: int
    yaku: list[YakuInfo]
    points: int
    limit: HandLimit
    yakuman_count: int | None = None


class PaoLiability(BaseModel):
    """
    What the seat liable (pao) for a winner's yakuman pays: the pao yakuman that made it liable (yaku_ids), all or half
    of the whole hand's value (share), and whether it also pays the winner's honba bonus.

    It names at least one pao yakuman, since a client rejects an empty list.
    """

    yaku_ids: list[int] = Field(min_length=1)
    share: PaoShare
    pays_honba: bool


class TsumoResult(BaseModel):
    """
    Result of a tsumo (self-draw) win.

    honba_bonus is the honba bonus the winner collected, every payer's together. pao_seat is the seat liable for the
    winner's yakuman and pao what it pays, both None without one.
    """

    type: RoundResultType = RoundResultType.TSUMO
    winner_seat: int
    hand_result: HandResultInfo
    scores: dict[int, int]
    score_changes: dict[int, int]
    riichi_sticks_collected: int
    closed_tiles: list[int]
    melds: list[int]
    win_tile: int
    honba_bonus: int
    pao_seat: int | None = None
    pao: PaoLiability | None = None
    ura_dora_indicators: list[int] | None = None


class RobbedKan(BaseModel):
    """
    A kan robbed by chankan, as its declarer declared it: an added kan, or a closed kan robbed by kokushi musou.

    A robbed kan never completes, so no meld event records it; the result of the ron that robbed it carries it instead.
    """

    seat: int
    tile_id: int
    kan_type: KanType


class RonResult(BaseModel):
    """
    Result of a ron (discard) win.

    robbed_kan is the kan the ron robbed, for a chankan; None for a ron on a discard. head_bumped_seats are the seats
    that also declared ron but lost it to head bump, in caller order; None when no declaration was bumped. honba_bonus
    is the honba bonus the winner collected; pao_seat is the seat liable for the winner's yakuman and pao what it pays,
    both None without one.
    """

    type: RoundResultType = RoundResultType.RON
    winner_seat: int
    loser_seat: int
    winning_tile: int
    hand_result: HandResultInfo
    scores: dict[int, int]
    score_changes: dict[int, int]
    riichi_sticks_collected: int
    closed_tiles: list[int]
    melds: list[int]
    honba_bonus: int
    pao_seat: int | None = None
    pao: PaoLiability | None = None
    ura_dora_indicators: list[int] | None = None
    robbed_kan: RobbedKan | None = None
    head_bumped_seats: list[int] | None = None


class DoubleRonWinner(BaseModel):
    """
    Per-winner data in a double ron result.

    score_changes is this winner's own payments alone (the loser's, a pao seat's, the winner's honba and any riichi
    sticks), so the winners' maps sum to the result's score_changes. honba_bonus, pao_seat and pao are this winner's, as
    on a single ron.
    """

    winner_seat: int
    hand_result: HandResultInfo
    score_changes: dict[int, int]
    riichi_sticks_collected: int
    closed_tiles: list[int]
    melds: list[int]
    honba_bonus: int
    pao_seat: int | None = None
    pao: PaoLiability | None = None
    ura_dora_indicators: list[int] | None = None


class DoubleRonResult(BaseModel):
    """
    Result of a double ron win.

    robbed_kan is the kan the rons robbed, for a chankan; None for rons on a discard. head_bumped_seats are the seats
    that also declared ron but lost it to head bump, in caller order; None when no declaration was bumped.
    """

    type: RoundResultType = RoundResultType.DOUBLE_RON
    loser_seat: int
    winning_tile: int
    winners: list[DoubleRonWinner]
    scores: dict[int, int]
    score_changes: dict[int, int]
    robbed_kan: RobbedKan | None = None
    head_bumped_seats: list[int] | None = None


class TenpaiHand(BaseModel):
    """
    Hand data for a tenpai player revealed at exhaustive draw.
    """

    seat: int
    closed_tiles: list[int]
    melds: list[int]


class ExhaustiveDrawResult(BaseModel):
    """
    Result of an exhaustive draw (wall empty).
    """

    type: RoundResultType = RoundResultType.EXHAUSTIVE_DRAW
    tempai_seats: list[int]
    noten_seats: list[int]
    tenpai_hands: list[TenpaiHand]
    scores: dict[int, int]
    score_changes: dict[int, int]


class AbortiveDrawResult(BaseModel):
    """
    Result of an abortive draw.

    seat is the seat that declared kyuushu kyuuhai; ron_seats are the seats that declared a triple ron, in caller order
    (counter-clockwise from the discarder), and robbed_kan the kan they robbed when the triple ron was a chankan. All
    stay None for every other draw.
    """

    type: RoundResultType = RoundResultType.ABORTIVE_DRAW
    reason: AbortiveDrawType
    scores: dict[int, int]
    score_changes: dict[int, int]
    seat: int | None = None
    ron_seats: list[int] | None = None
    robbed_kan: RobbedKan | None = None


class DiscardInfo(BaseModel):
    """
    A discard as it lies in its river: in the reconnect snapshot, and in a nagashi mangan's proof.
    """

    tile_id: int
    is_tsumogiri: bool = False
    is_riichi_discard: bool = False


class NagashiRiver(BaseModel):
    """
    The river of a seat that made nagashi mangan, every discard in it as it fell: the result's proof, so a client never
    shows it from its own table.
    """

    seat: int
    discards: list[DiscardInfo]


class NagashiManganResult(BaseModel):
    """
    Result of a nagashi mangan at exhaustive draw.

    rivers holds each qualifying seat's river, in the order of qualifying_seats.
    """

    type: RoundResultType = RoundResultType.NAGASHI_MANGAN
    qualifying_seats: list[int]
    rivers: list[NagashiRiver]
    tempai_seats: list[int]
    noten_seats: list[int]
    tenpai_hands: list[TenpaiHand]
    scores: dict[int, int]
    score_changes: dict[int, int]


class PlayerStanding(BaseModel):
    """
    Player standing in final game results.
    """

    seat: int
    score: int
    final_score: int


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

    seat: int
    call_type: MeldCallType
    options: tuple[tuple[int, int], ...] | None = None


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

    action: PlayerAction
    tiles: list[int] | None = None


class PlayerView(BaseModel):
    """
    Player-visible information about another player.
    """

    seat: int
    score: int


class PlayerReconnectState(BaseModel):
    """
    Per-player visible state in a reconnection snapshot.

    tile_count is the number of tiles in the player's closed hand (3n+2 while it holds its turn's draw), which other
    seats see face down but whose draws the snapshot does not replay.
    """

    seat: int
    score: int
    discards: list[DiscardInfo]
    melds: list[int]
    is_riichi: bool
    tile_count: int


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

    round_wind: WindName
    round_in_wind: int
    dealer_seat: int
    honba_sticks: int
    result_type: RoundResultType
    abortive_reason: AbortiveDrawType | None = None
    riichi_seats: tuple[int, ...]
    winner_seats: tuple[int, ...]
    loser_seat: int | None = None
    pao_seats: tuple[int, ...]
    tenpai_seats: tuple[int, ...] | None = None
    score_changes: dict[int, int]


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
    kan is the one record of it for the reconnected table. latest_discard_seat is the seat whose discard is the table's
    last action, which lies last in its river; None (absent on the wire) before the round's first discard, once a meld
    claimed the latest one and once the next seat drew. game_type and riichi_stick_value are the game's, and
    first_dealer_seat the game's first dealer, as game_started carries them.
    """

    game_id: str
    game_type: GameType
    players: list[GamePlayerInfo]
    dealer_seat: int
    first_dealer_seat: int
    dealer_dice: tuple[tuple[int, int], tuple[int, int]]
    riichi_stick_value: int
    seat: int
    round_wind: WindName
    round_number: int
    round_in_wind: int
    current_player_seat: int
    latest_discard_seat: int | None = None
    dora_indicators: list[int]
    honba_sticks: int
    riichi_sticks: int
    my_tiles: list[int]
    dice: tuple[int, int]
    tiles_remaining: int
    player_states: list[PlayerReconnectState]
    is_furiten: bool
    round_history: list[RoundHistoryEntry]
    result: RoundResult | None = None
