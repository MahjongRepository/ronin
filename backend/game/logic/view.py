from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.logic.decision import TurnAfterDraw
from game.logic.enums import RoundPhase, WindName
from game.logic.exceptions import DiscardHistoryError
from game.logic.meld_compact import frozen_meld_to_compact
from game.logic.state import round_in_wind, wind_name
from game.logic.state_utils import river_of
from game.logic.types import ExhaustiveDrawResult, NagashiManganResult
from game.logic.wall import tiles_remaining

if TYPE_CHECKING:
    from game.logic.decision import Decision
    from game.logic.enums import GamePhase
    from game.logic.state import MahjongGameState, MahjongRoundState
    from game.logic.types import DiscardInfo, RoundHistoryEntry, RoundResult


@dataclass(frozen=True)
class PublicSeat:
    """
    What every seat sees of one seat: its score, how many tiles its closed hand holds (seen face down), its river as the
    discards fell, its melds (packed) and whether it declared riichi.
    """

    seat: int
    score: int
    tile_count: int
    discards: tuple[DiscardInfo, ...]
    melds: tuple[int, ...]
    is_riichi: bool


@dataclass(frozen=True)
class RoundHeader:
    """
    The round a view shows: its number, wind, number within the wind (from 1), dealer, honba and dice.
    """

    round_number: int
    round_wind: WindName
    round_in_wind: int
    dealer_seat: int
    honba_sticks: int
    dice: tuple[int, int]


@dataclass(frozen=True)
class SeatView:
    """
    What one seat may see of the game: its own hand and decision, the public table, the round and the game.

    hand is the seat's closed hand, drawn_tile its turn's drawn tile (None off a turn after a draw), and is_furiten the
    furiten last reported to the seat. While the game waits on a round's end, round is the ended round's header and
    result its result, beside the scores and riichi sticks that result left; result is None while a round is in play.
    latest_discard_seat is the seat whose discard is the table's last action: None before the round's first discard,
    once a meld claimed the latest one and once the next seat drew. round_history holds every finished round in play
    order, the ended one included. decision is the seat's own decision, None when the game does not await it. A view
    never holds another seat's concealed tiles, offers or pending answers.
    """

    seat: int
    hand: tuple[int, ...]
    drawn_tile: int | None
    is_furiten: bool
    players: tuple[PublicSeat, ...]
    dora_indicators: tuple[int, ...]
    tiles_remaining: int
    riichi_sticks: int
    current_player_seat: int
    latest_discard_seat: int | None
    round: RoundHeader
    result: RoundResult | None
    game_phase: GamePhase
    first_dealer_seat: int
    dealer_dice: tuple[tuple[int, int], tuple[int, int]]
    round_history: tuple[RoundHistoryEntry, ...]
    decision: Decision | None


def build_seat_view(
    game_state: MahjongGameState,
    seat: int,
    *,
    is_furiten: bool,
    decision: Decision | None,
) -> SeatView:
    """
    Build the seat's view of the game from its state, the furiten last reported to the seat and its decision.
    """
    round_state = game_state.round_state
    players = tuple(
        PublicSeat(
            seat=p.seat,
            score=p.score,
            tile_count=len(p.tiles),
            discards=tuple(river_of(p)),
            melds=tuple(frozen_meld_to_compact(m) for m in p.melds),
            is_riichi=p.is_riichi,
        )
        for p in round_state.players
    )
    context = decision.context if decision is not None else None
    return SeatView(
        seat=seat,
        hand=round_state.players[seat].tiles,
        drawn_tile=context.drawn if isinstance(context, TurnAfterDraw) else None,
        is_furiten=is_furiten,
        players=players,
        dora_indicators=round_state.wall.dora_indicators,
        tiles_remaining=tiles_remaining(round_state.wall),
        riichi_sticks=game_state.riichi_sticks,
        current_player_seat=round_state.current_player_seat,
        latest_discard_seat=_latest_discard_seat(round_state),
        round=_round_header(game_state),
        result=round_state.result,
        game_phase=game_state.game_phase,
        first_dealer_seat=game_state.starting_dealer_seat,
        dealer_dice=game_state.dealer_dice,
        round_history=game_state.round_history,
        decision=decision,
    )


def _round_header(game_state: MahjongGameState) -> RoundHeader:
    """
    Return the header of the round a view shows: the round in play, or the one that ended.

    The round end has already moved the round number, dealer, wind and honba on to the next round, so an ended round's
    number is the one before and the rest come from its round history entry, taken before that advance. The next round
    is not dealt yet, so the wall and its dice are still the ended round's.
    """
    round_state = game_state.round_state
    if round_state.phase != RoundPhase.FINISHED:
        return RoundHeader(
            round_number=game_state.round_number,
            round_wind=wind_name(round_state.round_wind),
            round_in_wind=round_in_wind(game_state),
            dealer_seat=round_state.dealer_seat,
            honba_sticks=game_state.honba_sticks,
            dice=round_state.wall.dice,
        )

    ended = game_state.round_history[-1]
    return RoundHeader(
        round_number=game_state.round_number - 1,
        round_wind=ended.round_wind,
        round_in_wind=ended.round_in_wind,
        dealer_seat=ended.dealer_seat,
        honba_sticks=ended.honba_sticks,
        dice=round_state.wall.dice,
    )


def _latest_discard_seat(round_state: MahjongRoundState) -> int | None:
    """
    Return the seat whose discard is the table's last action, else None.

    all_discards holds the round's discarded tiles in play order, so its last is the latest discard. A meld that holds
    that tile claimed it, and then no discard is the latest, never the one before it. The next seat's draw is the next
    action: the turn passes to it only on that draw, so a current seat other than the discarder means the discard is no
    longer the latest action, except after an exhaustive draw, whose turn passed to a seat the empty wall gave no tile.
    A result on the discard itself (a ron, an abort) keeps it. Raises DiscardHistoryError when that unclaimed tile lies
    last in no river.
    """
    if not round_state.all_discards:
        return None

    tile_id = round_state.all_discards[-1]
    if any(tile_id in meld.tiles for player in round_state.players for meld in player.melds):
        return None

    discarder = next((p.seat for p in round_state.players if p.discards and p.discards[-1].tile_id == tile_id), None)
    if discarder is None:
        raise DiscardHistoryError(f"the latest discard {tile_id} lies last in no river")

    wall_ran_out = isinstance(round_state.result, ExhaustiveDrawResult | NagashiManganResult)
    if discarder != round_state.current_player_seat and not wall_ran_out:
        return None

    return discarder
