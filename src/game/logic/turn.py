"""
Turn loop orchestration for Mahjong game.
"""

from typing import TYPE_CHECKING

from game.logic.abortive import (
    AbortiveDrawType,
    can_call_kyuushu_kyuuhai,
    check_four_kans,
    check_four_riichi,
    check_four_winds,
    check_triple_ron,
    process_abortive_draw,
)
from game.logic.actions import get_available_actions
from game.logic.enums import CallType, KanType, MeldCallType, MeldViewType, PlayerAction
from game.logic.melds import (
    call_added_kan,
    call_chi,
    call_closed_kan,
    call_open_kan,
    call_pon,
    can_call_chi,
    can_call_open_kan,
    can_call_pon,
)
from game.logic.riichi import can_declare_riichi, declare_riichi
from game.logic.round import (
    advance_turn,
    check_exhaustive_draw,
    discard_tile,
    draw_tile,
    process_exhaustive_draw,
)
from game.logic.scoring import (
    apply_double_ron_score,
    apply_ron_score,
    apply_tsumo_score,
    calculate_hand_value,
)
from game.logic.state import RoundPhase
from game.logic.tiles import tile_to_34, tile_to_string
from game.logic.types import AvailableActionItem, MeldCaller
from game.logic.win import (
    can_call_ron,
    can_declare_tsumo,
    is_chankan_possible,
)
from game.messaging.events import (
    CallPromptEvent,
    DiscardEvent,
    DrawEvent,
    GameEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    TurnEvent,
)

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState, MahjongRoundState

# number of ron callers for double ron
DOUBLE_RON_COUNT = 2


def process_draw_phase(round_state: MahjongRoundState, game_state: MahjongGameState) -> list[GameEvent]:
    """
    Process the draw phase for the current player.

    Draws a tile and checks for available actions:
    - tsumo win
    - kyuushu kyuuhai (nine terminals abortive draw)
    - closed/added kan options

    Returns a list of typed events describing what happened and available options.
    """
    events: list[GameEvent] = []
    current_seat = round_state.current_player_seat
    player = round_state.players[current_seat]

    # check for exhaustive draw before attempting to draw
    if check_exhaustive_draw(round_state):
        result = process_exhaustive_draw(game_state)
        round_state.phase = RoundPhase.FINISHED
        events.append(RoundEndEvent(result=result, target="all"))
        return events

    # draw a tile
    drawn_tile = draw_tile(round_state)
    if drawn_tile is None:
        result = process_exhaustive_draw(game_state)
        round_state.phase = RoundPhase.FINISHED
        events.append(RoundEndEvent(result=result, target="all"))
        return events

    # notify player of drawn tile
    events.append(
        DrawEvent(
            seat=current_seat,
            tile_id=drawn_tile,
            tile=tile_to_string(drawn_tile),
            target=f"seat_{current_seat}",
        )
    )

    # build available actions for the player (already includes tsumo, riichi, kan options)
    available_actions = get_available_actions(round_state, game_state, current_seat)

    # check for kyuushu kyuuhai and add to actions if available
    if can_call_kyuushu_kyuuhai(player, round_state):
        available_actions.append(AvailableActionItem(action=PlayerAction.KYUUSHU))

    events.append(
        TurnEvent(
            current_seat=current_seat,
            available_actions=available_actions,
            wall_count=len(round_state.wall),
            target=f"seat_{current_seat}",
        )
    )

    return events


def process_discard_phase(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    tile_id: int,
    *,
    is_riichi: bool = False,
) -> list[GameEvent]:
    """
    Process the discard phase after a player discards a tile.

    Steps:
    1. If is_riichi: mark riichi step 1 (declared but not finalized)
    2. Validate and execute discard
    3. Check for four winds abortive draw
    4. Check for ron from other players
       - If 3 players can ron: triple ron abortive draw
       - If 1-2 players can ron: process win(s)
    5. If no ron and is_riichi: finalize riichi step 2
    6. Check for meld calls with priority: kan > pon > chi
    7. If no calls, advance turn

    Returns list of typed events describing what happened.
    """
    events: list[GameEvent] = []
    current_seat = round_state.current_player_seat
    player = round_state.players[current_seat]

    # step 1: mark riichi if declaring
    riichi_pending = False
    if is_riichi:
        if not can_declare_riichi(player, round_state):
            raise ValueError("cannot declare riichi: conditions not met")
        riichi_pending = True

    # step 2: execute discard
    discard = discard_tile(round_state, current_seat, tile_id, is_riichi=is_riichi)

    events.append(
        DiscardEvent(
            seat=current_seat,
            tile_id=tile_id,
            tile=tile_to_string(tile_id),
            is_tsumogiri=discard.is_tsumogiri,
            is_riichi=is_riichi,
        )
    )

    # step 3: check for four winds abortive draw
    if check_four_winds(round_state):
        result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_WINDS)
        round_state.phase = RoundPhase.FINISHED
        events.append(RoundEndEvent(result=result, target="all"))
        return events

    # step 4: check for ron from other players
    ron_callers = _find_ron_callers(round_state, tile_id, current_seat)

    if check_triple_ron(ron_callers):
        # triple ron is abortive draw
        result = process_abortive_draw(game_state, AbortiveDrawType.TRIPLE_RON)
        round_state.phase = RoundPhase.FINISHED
        events.append(RoundEndEvent(result=result, target="all"))
        return events

    if ron_callers:
        # ron opportunities exist - create call prompt
        events.append(
            CallPromptEvent(
                call_type=CallType.RON,
                tile_id=tile_id,
                from_seat=current_seat,
                callers=ron_callers,
                target="all",
            )
        )
        return events

    # step 5: finalize riichi if no ron
    if riichi_pending:
        declare_riichi(player, game_state)
        events.append(RiichiDeclaredEvent(seat=current_seat, target="all"))

        # check for four riichi abortive draw
        if check_four_riichi(round_state):
            result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_RIICHI)
            round_state.phase = RoundPhase.FINISHED
            events.append(RoundEndEvent(result=result, target="all"))
            return events

    # step 6: check for meld calls (priority: kan > pon > chi)
    meld_calls = _find_meld_callers(round_state, tile_id, current_seat)

    if meld_calls:
        events.append(
            CallPromptEvent(
                call_type=CallType.MELD,
                tile_id=tile_id,
                from_seat=current_seat,
                callers=meld_calls,
                target="all",
            )
        )
        return events

    # step 7: no calls, advance turn
    advance_turn(round_state)

    return events


class MeldCallContext:
    """Context for processing a meld call."""

    def __init__(
        self,
        round_state: MahjongRoundState,
        game_state: MahjongGameState,
        caller_seat: int,
        tile_id: int,
        sequence_tiles: tuple[int, int] | None = None,
    ) -> None:
        self.round_state = round_state
        self.game_state = game_state
        self.caller_seat = caller_seat
        self.tile_id = tile_id
        self.sequence_tiles = sequence_tiles
        self.discarder_seat = round_state.current_player_seat
        self.events: list[GameEvent] = []

    def check_four_kans_abort(self) -> bool:
        """Check for four kans abortive draw. Returns True if game should end."""
        if check_four_kans(self.round_state):
            result = process_abortive_draw(self.game_state, AbortiveDrawType.FOUR_KANS)
            self.round_state.phase = RoundPhase.FINISHED
            self.events.append(RoundEndEvent(result=result, target="all"))
            return True
        return False


def _process_pon_call(ctx: MeldCallContext) -> None:
    """Process pon call."""
    meld = call_pon(ctx.round_state, ctx.caller_seat, ctx.discarder_seat, ctx.tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        MeldEvent(
            meld_type=MeldViewType.PON,
            caller_seat=ctx.caller_seat,
            tile_ids=tile_ids,
            tiles=[tile_to_string(t) for t in tile_ids],
            from_seat=ctx.discarder_seat,
        )
    )


def _process_chi_call(ctx: MeldCallContext) -> None:
    """Process chi call."""
    if ctx.sequence_tiles is None:
        raise ValueError("chi call requires sequence_tiles")
    meld = call_chi(ctx.round_state, ctx.caller_seat, ctx.discarder_seat, ctx.tile_id, ctx.sequence_tiles)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        MeldEvent(
            meld_type=MeldViewType.CHI,
            caller_seat=ctx.caller_seat,
            tile_ids=tile_ids,
            tiles=[tile_to_string(t) for t in tile_ids],
            from_seat=ctx.discarder_seat,
        )
    )


def _process_open_kan_call(ctx: MeldCallContext) -> bool:
    """Process open kan call. Returns True if round ended."""
    meld = call_open_kan(ctx.round_state, ctx.caller_seat, ctx.discarder_seat, ctx.tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=ctx.caller_seat,
            tile_ids=tile_ids,
            tiles=[tile_to_string(t) for t in tile_ids],
            from_seat=ctx.discarder_seat,
            kan_type=KanType.OPEN,
        )
    )
    return ctx.check_four_kans_abort()


def _process_closed_kan_call(ctx: MeldCallContext) -> bool:
    """Process closed kan call. Returns True if round ended."""
    meld = call_closed_kan(ctx.round_state, ctx.caller_seat, ctx.tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=ctx.caller_seat,
            tile_ids=tile_ids,
            tiles=[tile_to_string(t) for t in tile_ids],
            kan_type=KanType.CLOSED,
        )
    )
    return ctx.check_four_kans_abort()


def _process_added_kan_call(ctx: MeldCallContext) -> bool:
    """Process added kan call. Returns True if round ended or waiting for chankan."""
    chankan_seats = is_chankan_possible(ctx.round_state, ctx.caller_seat, ctx.tile_id)
    if chankan_seats:
        ctx.events.append(
            CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=ctx.tile_id,
                from_seat=ctx.caller_seat,
                callers=chankan_seats,
                target="all",
            )
        )
        return True

    meld = call_added_kan(ctx.round_state, ctx.caller_seat, ctx.tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    ctx.events.append(
        MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=ctx.caller_seat,
            tile_ids=tile_ids,
            tiles=[tile_to_string(t) for t in tile_ids],
            kan_type=KanType.ADDED,
        )
    )
    return ctx.check_four_kans_abort()


def process_meld_call(  # noqa: PLR0913
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    call_type: MeldCallType,
    tile_id: int,
    *,
    sequence_tiles: tuple[int, int] | None = None,
) -> list[GameEvent]:
    """
    Process a meld call (pon, chi, open kan, closed kan, added kan).

    For pon/chi/open kan: the tile_id is the discarded tile being called.
    For closed kan: tile_id is one of the 4 tiles to kan.
    For added kan: tile_id is the 4th tile to add to existing pon.

    Returns typed events describing the meld and any follow-up (chankan check for added kan).
    """
    ctx = MeldCallContext(round_state, game_state, caller_seat, tile_id, sequence_tiles)

    if call_type == MeldCallType.PON:
        _process_pon_call(ctx)
    elif call_type == MeldCallType.CHI:
        _process_chi_call(ctx)
    elif call_type == MeldCallType.OPEN_KAN:
        if _process_open_kan_call(ctx):
            return ctx.events
    elif call_type == MeldCallType.CLOSED_KAN:
        if _process_closed_kan_call(ctx):
            return ctx.events
    elif call_type == MeldCallType.ADDED_KAN:
        if _process_added_kan_call(ctx):
            return ctx.events
    else:
        raise ValueError(f"unknown call_type: {call_type}")

    return ctx.events


def process_ron_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    ron_callers: list[int],
    tile_id: int,
    discarder_seat: int,
) -> list[GameEvent]:
    """
    Process ron call(s) from one or more players.

    Returns typed events for the ron result.
    """
    events: list[GameEvent] = []

    if len(ron_callers) == 1:
        # single ron
        winner_seat = ron_callers[0]
        winner = round_state.players[winner_seat]

        # temporarily add the tile to calculate hand value
        winner.tiles.append(tile_id)
        hand_result = calculate_hand_value(winner, round_state, tile_id, is_tsumo=False)
        winner.tiles.remove(tile_id)

        if hand_result.error:
            raise ValueError(f"ron calculation error: {hand_result.error}")

        result = apply_ron_score(game_state, winner_seat, discarder_seat, hand_result)
        round_state.phase = RoundPhase.FINISHED
        events.append(RoundEndEvent(result=result, target="all"))

    elif len(ron_callers) == DOUBLE_RON_COUNT:
        # double ron
        winners = []
        for winner_seat in ron_callers:
            winner = round_state.players[winner_seat]
            winner.tiles.append(tile_id)
            hand_result = calculate_hand_value(winner, round_state, tile_id, is_tsumo=False)
            winner.tiles.remove(tile_id)

            if hand_result.error:
                raise ValueError(f"ron calculation error for seat {winner_seat}: {hand_result.error}")

            winners.append((winner_seat, hand_result))

        result = apply_double_ron_score(game_state, winners, discarder_seat)
        round_state.phase = RoundPhase.FINISHED
        events.append(RoundEndEvent(result=result, target="all"))

    return events


def process_tsumo_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    winner_seat: int,
) -> list[GameEvent]:
    """
    Process tsumo declaration from a player.

    Returns typed events for the tsumo result.
    """
    events: list[GameEvent] = []
    winner = round_state.players[winner_seat]

    if not can_declare_tsumo(winner, round_state):
        raise ValueError("cannot declare tsumo: conditions not met")

    # clear pending dora: tsumo win (e.g. rinshan kaihou after open/added kan)
    # scores before the deferred dora indicator would have been revealed
    round_state.pending_dora_count = 0

    # the win tile is the last tile in hand (just drawn)
    win_tile = winner.tiles[-1]
    hand_result = calculate_hand_value(winner, round_state, win_tile, is_tsumo=True)

    if hand_result.error:
        raise ValueError(f"tsumo calculation error: {hand_result.error}")

    result = apply_tsumo_score(game_state, winner_seat, hand_result)
    round_state.phase = RoundPhase.FINISHED
    events.append(RoundEndEvent(result=result, target="all"))

    return events


def _find_ron_callers(round_state: MahjongRoundState, tile_id: int, discarder_seat: int) -> list[int]:
    """
    Find all players who can call ron on the discarded tile.

    Returns list of seat numbers sorted by priority (counter-clockwise from discarder).
    """
    ron_callers = []

    for seat in range(4):
        if seat == discarder_seat:
            continue

        player = round_state.players[seat]
        if can_call_ron(player, tile_id, round_state):
            ron_callers.append(seat)

    # sort by priority: counter-clockwise from discarder (closer = higher priority)
    def distance_from_discarder(s: int) -> int:
        return (s - discarder_seat) % 4

    ron_callers.sort(key=distance_from_discarder)

    return ron_callers


def _find_meld_callers(
    round_state: MahjongRoundState,
    tile_id: int,
    discarder_seat: int,
) -> list[MeldCaller]:
    """
    Find all players who can call a meld on the discarded tile.

    Returns list of meld options sorted by priority (kan > pon > chi).
    Each entry includes: seat, call_type, and options (for chi).
    """
    meld_calls: list[MeldCaller] = []
    tile_34 = tile_to_34(tile_id)

    for seat in range(4):
        if seat == discarder_seat:
            continue

        player = round_state.players[seat]

        # check open kan
        if can_call_open_kan(player, tile_id, round_state):
            meld_calls.append(
                MeldCaller(
                    seat=seat,
                    call_type=MeldCallType.OPEN_KAN,
                    tile_34=tile_34,
                    priority=0,
                )
            )

        # check pon
        if can_call_pon(player, tile_id):
            meld_calls.append(
                MeldCaller(
                    seat=seat,
                    call_type=MeldCallType.PON,
                    tile_34=tile_34,
                    priority=1,
                )
            )

        # check chi (only from kamicha)
        chi_options = can_call_chi(player, tile_id, discarder_seat, seat)
        if chi_options:
            meld_calls.append(
                MeldCaller(
                    seat=seat,
                    call_type=MeldCallType.CHI,
                    tile_34=tile_34,
                    options=chi_options,
                    priority=2,
                )
            )

    # sort by priority
    meld_calls.sort(key=lambda x: x.priority)

    return meld_calls
