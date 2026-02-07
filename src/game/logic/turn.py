"""
Turn loop orchestration for Mahjong game.
"""

from __future__ import annotations

import logging

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
from game.logic.enums import (
    MELD_CALL_PRIORITY,
    CallType,
    KanType,
    MeldCallType,
    MeldViewType,
    PlayerAction,
    RoundPhase,
)
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    DoraRevealedEvent,
    DrawEvent,
    GameEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    TurnEvent,
)
from game.logic.exceptions import InvalidActionError, InvalidMeldError, InvalidRiichiError, InvalidWinError
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
    check_exhaustive_draw,
    discard_tile,
    draw_tile,
    process_exhaustive_draw,
    reveal_pending_dora,
)
from game.logic.scoring import (
    apply_double_ron_score,
    apply_ron_score,
    apply_tsumo_score,
    calculate_hand_value,
    calculate_hand_value_with_tiles,
)
from game.logic.state import (
    MahjongGameState,
    MahjongRoundState,
    PendingCallPrompt,
)
from game.logic.state_utils import (
    advance_turn,
    update_player,
)
from game.logic.tiles import tile_to_34
from game.logic.types import AvailableActionItem, MeldCaller
from game.logic.win import (
    all_tiles_from_hand_and_melds,
    can_call_ron,
    can_declare_tsumo,
    get_waiting_tiles,
    is_chankan_possible,
)

logger = logging.getLogger(__name__)

# number of ron callers for double ron
DOUBLE_RON_COUNT = 2


def emit_deferred_dora_events(
    round_state: MahjongRoundState,
) -> tuple[MahjongRoundState, list[GameEvent]]:
    """
    Reveal deferred dora indicators (from open/added kan) and emit events.

    Called after a discard passes the ron check. Under our rules,
    open/added kan dora is revealed only after the replacement discard
    is accepted (not ron'd).

    Returns (new_round_state, events).
    """
    new_state, revealed = reveal_pending_dora(round_state)

    events: list[GameEvent] = [
        DoraRevealedEvent(
            tile_id=dora_tile_id,
            dora_indicators=list(new_state.dora_indicators),
        )
        for dora_tile_id in revealed
    ]

    return new_state, events


def process_draw_phase(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process the draw phase for the current player.

    Draws a tile and checks for available actions:
    - tsumo win
    - kyuushu kyuuhai (nine terminals abortive draw)
    - closed/added kan options

    Returns (new_round_state, new_game_state, events).
    """
    events: list[GameEvent] = []
    current_seat = round_state.current_player_seat

    # check for exhaustive draw before attempting to draw
    if check_exhaustive_draw(round_state):
        new_round_state, new_game_state, result = process_exhaustive_draw(game_state)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))
        return new_round_state, new_game_state, events

    # draw a tile
    new_round_state, drawn_tile = draw_tile(round_state)
    if drawn_tile is None:  # pragma: no cover
        raise AssertionError("drawn_tile is None after exhaustive draw check passed")

    # notify player of drawn tile
    events.append(
        DrawEvent(
            seat=current_seat,
            tile_id=drawn_tile,
            target=f"seat_{current_seat}",
        )
    )

    # update game state with new round state
    new_game_state = game_state.model_copy(update={"round_state": new_round_state})

    # build available actions for the player (already includes tsumo, riichi, kan options)
    available_actions = get_available_actions(new_round_state, new_game_state, current_seat)

    # check for kyuushu kyuuhai and add to actions if available
    player = new_round_state.players[current_seat]
    if can_call_kyuushu_kyuuhai(player, new_round_state):
        available_actions.append(AvailableActionItem(action=PlayerAction.KYUUSHU))

    events.append(
        TurnEvent(
            current_seat=current_seat,
            available_actions=available_actions,
            wall_count=len(new_round_state.wall),
            target=f"seat_{current_seat}",
        )
    )

    return new_round_state, new_game_state, events


def _check_riichi_furiten(
    round_state: MahjongRoundState,
    tile_id: int,
    discarder_seat: int,
    ron_callers: list[int],
) -> MahjongRoundState:
    """
    Set riichi furiten for riichi players whose winning tile just passed.

    A riichi player who is waiting on the discarded tile but did not (or could not)
    call ron becomes permanently furiten for the rest of the hand.

    Returns new round state with updated furiten flags.
    """
    tile_34 = tile_to_34(tile_id)
    new_state = round_state

    for seat in range(4):
        if seat == discarder_seat:
            continue
        player = new_state.players[seat]
        if not player.is_riichi:
            continue
        if seat in ron_callers:
            # they can call ron; riichi furiten only applies if they later pass
            continue
        waiting = get_waiting_tiles(player)
        if tile_34 in waiting:
            new_state = update_player(new_state, seat, is_riichi_furiten=True)

    return new_state


def _find_meld_callers(
    round_state: MahjongRoundState,
    tile_id: int,
    discarder_seat: int,
) -> list[MeldCaller]:
    """
    Find all players who can call a meld on the discarded tile.

    Returns list of MeldCaller options sorted by priority (kan > pon > chi).
    Each entry includes: seat, call_type, and options (for chi).
    """
    meld_calls: list[MeldCaller] = []

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
                )
            )

        # check pon
        if can_call_pon(player, tile_id):
            meld_calls.append(
                MeldCaller(
                    seat=seat,
                    call_type=MeldCallType.PON,
                )
            )

        # check chi (only from kamicha)
        chi_options = can_call_chi(player, tile_id, discarder_seat, seat)
        if chi_options:
            meld_calls.append(
                MeldCaller(
                    seat=seat,
                    call_type=MeldCallType.CHI,
                    options=tuple(chi_options),
                )
            )

    # sort by priority: kan > pon > chi
    meld_calls.sort(key=lambda x: MELD_CALL_PRIORITY.get(x.call_type, 99))

    return meld_calls


def process_discard_phase(  # noqa: PLR0915
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    tile_id: int,
    *,
    is_riichi: bool = False,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process the discard phase after a player discards a tile.

    Steps:
    1. If is_riichi: mark riichi step 1 (declared but not finalized)
    2. Validate and execute discard
    3. Check for four winds abortive draw
    4. Check for ron from other players
       - If 3 players can ron: triple ron abortive draw
       - If 1-2 players can ron: set up pending prompt (dora NOT revealed yet)
    5. Reveal deferred dora (from open/added kan) now that the discard passed
    6. If no ron and is_riichi: finalize riichi step 2
    7. Check for meld calls with priority: kan > pon > chi
    8. If no calls, advance turn

    Returns (new_round_state, new_game_state, events).
    """
    events: list[GameEvent] = []
    current_seat = round_state.current_player_seat
    player = round_state.players[current_seat]
    new_round_state = round_state
    new_game_state = game_state

    # step 1: mark riichi if declaring
    riichi_pending = False
    if is_riichi:
        if not can_declare_riichi(player, round_state):
            logger.error(f"seat {current_seat} cannot declare riichi: conditions not met")
            raise InvalidRiichiError("cannot declare riichi: conditions not met")
        riichi_pending = True

    # step 2: execute discard
    new_round_state, discard = discard_tile(new_round_state, current_seat, tile_id, is_riichi=is_riichi)
    new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})

    events.append(
        DiscardEvent(
            seat=current_seat,
            tile_id=tile_id,
            is_tsumogiri=discard.is_tsumogiri,
            is_riichi=is_riichi,
        )
    )

    # step 3: check for four winds abortive draw
    if check_four_winds(new_round_state):
        result = process_abortive_draw(new_game_state, AbortiveDrawType.FOUR_WINDS)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))
        return new_round_state, new_game_state, events

    # step 4: check for ron from other players
    ron_callers = _find_ron_callers(new_round_state, tile_id, current_seat)

    # set riichi furiten for riichi players whose winning tile passed
    new_round_state = _check_riichi_furiten(new_round_state, tile_id, current_seat, ron_callers)
    new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})

    if check_triple_ron(ron_callers):
        # triple ron is abortive draw
        result = process_abortive_draw(new_game_state, AbortiveDrawType.TRIPLE_RON)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))
        return new_round_state, new_game_state, events

    if ron_callers:
        # ron opportunities exist - set up pending prompt and create call prompt event
        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=tile_id,
            from_seat=current_seat,
            pending_seats=frozenset(ron_callers),
            callers=tuple(ron_callers),
        )
        new_round_state = new_round_state.model_copy(update={"pending_call_prompt": prompt})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(
            CallPromptEvent(
                call_type=CallType.RON,
                tile_id=tile_id,
                from_seat=current_seat,
                callers=ron_callers,
                target="all",
            )
        )
        return new_round_state, new_game_state, events

    # step 5: reveal deferred dora (from open/added kan) now that the discard passed
    new_round_state, dora_events = emit_deferred_dora_events(new_round_state)
    events.extend(dora_events)
    new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})

    # step 6: finalize riichi if no ron
    if riichi_pending:
        new_round_state, new_game_state = declare_riichi(new_round_state, new_game_state, current_seat)
        events.append(RiichiDeclaredEvent(seat=current_seat, target="all"))

        # check for four riichi abortive draw
        if check_four_riichi(new_round_state):
            result = process_abortive_draw(new_game_state, AbortiveDrawType.FOUR_RIICHI)
            new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
            new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
            events.append(RoundEndEvent(result=result, target="all"))
            return new_round_state, new_game_state, events

    # step 7: check for meld calls (priority: kan > pon > chi)
    meld_calls = _find_meld_callers(new_round_state, tile_id, current_seat)

    if meld_calls:
        # set up pending prompt and create call prompt event
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=current_seat,
            pending_seats=frozenset(c.seat for c in meld_calls),
            callers=tuple(meld_calls),
        )
        new_round_state = new_round_state.model_copy(update={"pending_call_prompt": prompt})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(
            CallPromptEvent(
                call_type=CallType.MELD,
                tile_id=tile_id,
                from_seat=current_seat,
                callers=meld_calls,
                target="all",
            )
        )
        return new_round_state, new_game_state, events

    # step 8: no calls, advance turn
    new_round_state = advance_turn(new_round_state)
    new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})

    return new_round_state, new_game_state, events


def _find_ron_callers(
    round_state: MahjongRoundState,
    tile_id: int,
    discarder_seat: int,
) -> list[int]:
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


def process_ron_call(  # noqa: PLR0913
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    ron_callers: list[int],
    tile_id: int,
    discarder_seat: int,
    *,
    is_chankan: bool = False,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process ron call(s) from one or more players.

    Uses local tile copies for hand calculation.

    Returns (new_round_state, new_game_state, events).
    """
    events: list[GameEvent] = []

    if len(ron_callers) == 1:
        # single ron
        winner_seat = ron_callers[0]
        winner = round_state.players[winner_seat]

        # build complete tile list with the ron tile added (closed hand + melds + win tile)
        tiles_with_win = all_tiles_from_hand_and_melds([*list(winner.tiles), tile_id], winner.melds)

        # calculate hand value using explicit tiles list
        hand_result = calculate_hand_value_with_tiles(
            winner, round_state, tiles_with_win, tile_id, is_tsumo=False, is_chankan=is_chankan
        )

        if hand_result.error:
            logger.error(
                f"ron calculation error for seat {winner_seat}: {hand_result.error}, "
                f"tiles={tiles_with_win}, melds={winner.melds}, win_tile={tile_id}"
            )
            raise InvalidWinError(f"ron calculation error: {hand_result.error}")

        new_round_state, new_game_state, result = apply_ron_score(
            game_state, winner_seat, discarder_seat, hand_result
        )
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))

    elif len(ron_callers) == DOUBLE_RON_COUNT:
        # double ron
        winners = []
        for winner_seat in ron_callers:
            winner = round_state.players[winner_seat]

            # build complete tile list with the ron tile added (closed hand + melds + win tile)
            tiles_with_win = all_tiles_from_hand_and_melds([*list(winner.tiles), tile_id], winner.melds)

            # calculate hand value using explicit tiles list
            hand_result = calculate_hand_value_with_tiles(
                winner, round_state, tiles_with_win, tile_id, is_tsumo=False, is_chankan=is_chankan
            )

            if hand_result.error:
                logger.error(
                    f"ron calculation error for seat {winner_seat}: {hand_result.error}, "
                    f"tiles={tiles_with_win}, melds={winner.melds}, win_tile={tile_id}"
                )
                raise InvalidWinError(f"ron calculation error for seat {winner_seat}: {hand_result.error}")

            winners.append((winner_seat, hand_result))

        new_round_state, new_game_state, result = apply_double_ron_score(game_state, winners, discarder_seat)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))
    else:  # pragma: no cover
        raise AssertionError("process_ron_call called with no valid winner count")

    return new_round_state, new_game_state, events


def process_tsumo_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    winner_seat: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process tsumo declaration from a player.

    Returns (new_round_state, new_game_state, events).
    """
    events: list[GameEvent] = []
    winner = round_state.players[winner_seat]

    if not can_declare_tsumo(winner, round_state):
        logger.error(
            f"seat {winner_seat} cannot declare tsumo: conditions not met, "
            f"tiles={winner.tiles}, melds={winner.melds}"
        )
        raise InvalidWinError("cannot declare tsumo: conditions not met")

    # clear pending dora: tsumo win (e.g. rinshan kaihou after open/added kan)
    # scores before the deferred dora indicator would have been revealed
    new_round_state = round_state.model_copy(update={"pending_dora_count": 0})

    # the win tile is the last tile in hand (just drawn)
    win_tile = winner.tiles[-1]
    hand_result = calculate_hand_value(winner, new_round_state, win_tile, is_tsumo=True)

    if hand_result.error:
        logger.error(
            f"tsumo calculation error for seat {winner_seat}: {hand_result.error}, "
            f"tiles={winner.tiles}, melds={winner.melds}, win_tile={win_tile}"
        )
        raise InvalidWinError(f"tsumo calculation error: {hand_result.error}")

    # apply score changes
    new_game_state = game_state.model_copy(update={"round_state": new_round_state})
    new_round_state, new_game_state, result = apply_tsumo_score(new_game_state, winner_seat, hand_result)
    new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
    new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
    events.append(RoundEndEvent(result=result, target="all"))

    return new_round_state, new_game_state, events


def _process_pon_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle a pon meld call."""
    new_round_state, meld = call_pon(round_state, caller_seat, discarder_seat, tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.PON,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            from_seat=discarder_seat,
            called_tile_id=tile_id,
        )
    ]
    return new_round_state, game_state.model_copy(update={"round_state": new_round_state}), events


def _process_chi_call(  # noqa: PLR0913
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
    sequence_tiles: tuple[int, int],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle a chi meld call."""
    new_round_state, meld = call_chi(round_state, caller_seat, discarder_seat, tile_id, sequence_tiles)
    tile_ids = list(meld.tiles) if meld.tiles else []
    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.CHI,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            from_seat=discarder_seat,
            called_tile_id=tile_id,
        )
    ]
    return new_round_state, game_state.model_copy(update={"round_state": new_round_state}), events


def _check_four_kans_abort(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    events: list[GameEvent],
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent], bool]:
    """Check for four kans abortive draw. Return (round, game, events, aborted)."""
    if check_four_kans(round_state):
        new_game_state = game_state.model_copy(update={"round_state": round_state})
        result = process_abortive_draw(new_game_state, AbortiveDrawType.FOUR_KANS)
        new_round_state = round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = new_game_state.model_copy(update={"round_state": new_round_state})
        events.append(RoundEndEvent(result=result, target="all"))
        return new_round_state, new_game_state, events, True
    return round_state, game_state, events, False


def _process_open_kan_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle an open kan meld call."""
    new_round_state, meld = call_open_kan(round_state, caller_seat, discarder_seat, tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            from_seat=discarder_seat,
            kan_type=KanType.OPEN,
            called_tile_id=tile_id,
        )
    ]
    new_round_state, new_game_state, events, _aborted = _check_four_kans_abort(
        new_round_state, game_state, events
    )
    return new_round_state, new_game_state, events


def _process_closed_kan_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle a closed kan meld call."""
    new_round_state, meld = call_closed_kan(round_state, caller_seat, tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            kan_type=KanType.CLOSED,
        ),
        DoraRevealedEvent(
            tile_id=new_round_state.dora_indicators[-1],
            dora_indicators=list(new_round_state.dora_indicators),
        ),
    ]
    new_round_state, new_game_state, events, _aborted = _check_four_kans_abort(
        new_round_state, game_state, events
    )
    return new_round_state, new_game_state, events


def _process_added_kan_call(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """Handle an added kan meld call."""
    # check for chankan first (using current state before kan is executed)
    chankan_seats = is_chankan_possible(round_state, caller_seat, tile_id)
    if chankan_seats:
        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=tile_id,
            from_seat=caller_seat,
            pending_seats=frozenset(chankan_seats),
            callers=tuple(chankan_seats),
        )
        new_round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        new_game_state = game_state.model_copy(update={"round_state": new_round_state})
        events: list[GameEvent] = [
            CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=tile_id,
                from_seat=caller_seat,
                callers=chankan_seats,
                target="all",
            )
        ]
        return new_round_state, new_game_state, events

    new_round_state, meld = call_added_kan(round_state, caller_seat, tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []
    events = [
        MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            kan_type=KanType.ADDED,
        )
    ]
    new_round_state, new_game_state, events, _aborted = _check_four_kans_abort(
        new_round_state, game_state, events
    )
    return new_round_state, new_game_state, events


def process_meld_call(  # noqa: PLR0913
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    call_type: MeldCallType,
    tile_id: int,
    *,
    sequence_tiles: tuple[int, int] | None = None,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Process a meld call (pon, chi, open kan, closed kan, added kan).

    For pon/chi/open kan: the tile_id is the discarded tile being called.
    For closed kan: tile_id is one of the 4 tiles to kan.
    For added kan: tile_id is the 4th tile to add to existing pon.

    Returns (new_round_state, new_game_state, events).
    """
    discarder_seat = round_state.current_player_seat

    if call_type == MeldCallType.PON:
        return _process_pon_call(round_state, game_state, caller_seat, discarder_seat, tile_id)

    if call_type == MeldCallType.CHI:
        if sequence_tiles is None:
            logger.error(f"chi call from seat {caller_seat} missing sequence_tiles")
            raise InvalidMeldError("chi call requires sequence_tiles")
        return _process_chi_call(
            round_state, game_state, caller_seat, discarder_seat, tile_id, sequence_tiles
        )

    if call_type == MeldCallType.OPEN_KAN:
        return _process_open_kan_call(round_state, game_state, caller_seat, discarder_seat, tile_id)

    if call_type == MeldCallType.CLOSED_KAN:
        return _process_closed_kan_call(round_state, game_state, caller_seat, tile_id)

    if call_type == MeldCallType.ADDED_KAN:
        return _process_added_kan_call(round_state, game_state, caller_seat, tile_id)

    logger.error(f"unknown call_type: {call_type} from seat {caller_seat}")  # pragma: no cover
    raise InvalidActionError(f"unknown call_type: {call_type}")  # pragma: no cover
