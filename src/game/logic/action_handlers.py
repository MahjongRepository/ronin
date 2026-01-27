"""
Action handlers for game actions.

Each handler validates input and returns a list of GameEvent objects.
These handlers are designed to be used by the MahjongGameService to process player actions.
"""

from typing import Any, NamedTuple

from game.logic.abortive import (
    AbortiveDrawType,
    call_kyuushu_kyuuhai,
    can_call_kyuushu_kyuuhai,
    check_four_kans,
    check_four_riichi,
    process_abortive_draw,
)
from game.logic.actions import get_available_actions
from game.logic.melds import call_added_kan
from game.logic.riichi import declare_riichi
from game.logic.round import advance_turn
from game.logic.state import MahjongGameState, MahjongRoundState, RoundPhase
from game.logic.tiles import tile_to_string
from game.logic.turn import (
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
    process_tsumo_call,
)
from game.messaging.events import (
    DrawEvent,
    ErrorEvent,
    GameEvent,
    MeldEvent,
    PassAcknowledgedEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    TurnEvent,
)

# hand size after discard (waiting for call response)
HAND_SIZE_AFTER_DISCARD = 13


class ActionResult(NamedTuple):
    """Result of an action handler execution."""

    events: list[GameEvent]
    needs_post_discard: bool = False


def _create_turn_event(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> TurnEvent:
    """Create a turn event for a player."""
    available_actions = get_available_actions(round_state, game_state, seat)
    return TurnEvent(
        current_seat=seat,
        available_actions=available_actions,
        wall_count=len(round_state.wall),
        target=f"seat_{seat}",
    )


def handle_discard(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: dict[str, Any],
) -> ActionResult:
    """
    Handle a discard action.

    Validates the player's turn and tile_id, then processes the discard.
    Returns events and whether post-discard processing is needed.
    """
    if round_state.current_player_seat != seat:
        return ActionResult(
            [ErrorEvent(code="not_your_turn", message="not your turn", target=f"seat_{seat}")]
        )

    tile_id = data.get("tile_id")
    if tile_id is None:
        return ActionResult(
            [ErrorEvent(code="missing_tile_id", message="tile_id required", target=f"seat_{seat}")]
        )

    try:
        events = process_discard_phase(round_state, game_state, tile_id, is_riichi=False)
        return ActionResult(events, needs_post_discard=True)
    except ValueError as e:
        return ActionResult([ErrorEvent(code="invalid_discard", message=str(e), target=f"seat_{seat}")])


def handle_riichi(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: dict[str, Any],
) -> ActionResult:
    """
    Handle a riichi declaration with discard.

    Validates the player's turn and tile_id, then processes the riichi discard.
    """
    if round_state.current_player_seat != seat:
        return ActionResult(
            [ErrorEvent(code="not_your_turn", message="not your turn", target=f"seat_{seat}")]
        )

    tile_id = data.get("tile_id")
    if tile_id is None:
        return ActionResult(
            [ErrorEvent(code="missing_tile_id", message="tile_id required", target=f"seat_{seat}")]
        )

    try:
        events = process_discard_phase(round_state, game_state, tile_id, is_riichi=True)
        return ActionResult(events, needs_post_discard=True)
    except ValueError as e:
        return ActionResult([ErrorEvent(code="invalid_riichi", message=str(e), target=f"seat_{seat}")])


def handle_tsumo(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> ActionResult:
    """
    Handle a tsumo declaration.

    Validates the player's turn and processes the tsumo win.
    """
    if round_state.current_player_seat != seat:
        return ActionResult(
            [ErrorEvent(code="not_your_turn", message="not your turn", target=f"seat_{seat}")]
        )

    try:
        events = process_tsumo_call(round_state, game_state, seat)
        return ActionResult(events)
    except ValueError as e:
        return ActionResult([ErrorEvent(code="invalid_tsumo", message=str(e), target=f"seat_{seat}")])


def handle_ron(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: dict[str, Any],
) -> ActionResult:
    """
    Handle a ron call from a player.

    Validates tile_id and from_seat, then processes the ron win.
    """
    tile_id = data.get("tile_id")
    discarder_seat = data.get("from_seat")

    if tile_id is None or discarder_seat is None:
        return ActionResult(
            [
                ErrorEvent(
                    code="missing_params", message="tile_id and from_seat required", target=f"seat_{seat}"
                )
            ]
        )

    try:
        events = process_ron_call(round_state, game_state, [seat], tile_id, discarder_seat)
        return ActionResult(events)
    except ValueError as e:
        return ActionResult([ErrorEvent(code="invalid_ron", message=str(e), target=f"seat_{seat}")])


def handle_pon(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: dict[str, Any],
) -> ActionResult:
    """
    Handle a pon call from a player.

    Validates tile_id and processes the pon meld.
    Returns meld events and a turn event for the caller.
    """
    tile_id = data.get("tile_id")
    if tile_id is None:
        return ActionResult(
            [ErrorEvent(code="missing_tile_id", message="tile_id required", target=f"seat_{seat}")]
        )

    try:
        events = process_meld_call(round_state, game_state, seat, "pon", tile_id)
        events.append(_create_turn_event(round_state, game_state, seat))
        return ActionResult(events)
    except ValueError as e:
        return ActionResult([ErrorEvent(code="invalid_pon", message=str(e), target=f"seat_{seat}")])


def handle_chi(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: dict[str, Any],
) -> ActionResult:
    """
    Handle a chi call from a player.

    Validates tile_id and sequence_tiles, then processes the chi meld.
    Returns meld events and a turn event for the caller.
    """
    tile_id = data.get("tile_id")
    sequence_tiles = data.get("sequence_tiles")

    if tile_id is None or sequence_tiles is None:
        return ActionResult(
            [
                ErrorEvent(
                    code="missing_params",
                    message="tile_id and sequence_tiles required",
                    target=f"seat_{seat}",
                )
            ]
        )

    try:
        events = process_meld_call(
            round_state, game_state, seat, "chi", tile_id, sequence_tiles=tuple(sequence_tiles)
        )
        events.append(_create_turn_event(round_state, game_state, seat))
        return ActionResult(events)
    except ValueError as e:
        return ActionResult([ErrorEvent(code="invalid_chi", message=str(e), target=f"seat_{seat}")])


def handle_kan(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: dict[str, Any],
) -> ActionResult:
    """
    Handle a kan call (open, closed, or added).

    Validates tile_id and kan_type, then processes the kan meld.
    Returns meld events and handles post-kan processing (chankan, dead wall draw).
    """
    tile_id = data.get("tile_id")
    kan_type = data.get("kan_type", "open")

    if tile_id is None:
        return ActionResult(
            [ErrorEvent(code="missing_tile_id", message="tile_id required", target=f"seat_{seat}")]
        )

    try:
        events = process_meld_call(round_state, game_state, seat, f"{kan_type}_kan", tile_id)
    except ValueError as e:
        return ActionResult([ErrorEvent(code="invalid_kan", message=str(e), target=f"seat_{seat}")])

    # check if round ended (four kans or chankan)
    if round_state.phase == RoundPhase.FINISHED:
        return ActionResult(events)

    # check for chankan prompt in events
    has_chankan_prompt = any(
        e.type == "call_prompt" and getattr(e, "call_type", None) == "chankan" for e in events
    )
    if has_chankan_prompt:
        # return events with chankan prompt - caller will handle responses
        return ActionResult(events)

    # after kan, emit draw event for the dead wall tile, then turn event
    if round_state.phase == RoundPhase.PLAYING:
        player = round_state.players[seat]
        if player.tiles:
            drawn_tile = player.tiles[-1]
            events.append(
                DrawEvent(
                    seat=seat,
                    tile_id=drawn_tile,
                    tile=tile_to_string(drawn_tile),
                    target=f"seat_{seat}",
                )
            )
        events.append(_create_turn_event(round_state, game_state, seat))

    return ActionResult(events)


def handle_kyuushu(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> ActionResult:
    """
    Handle kyuushu kyuuhai (nine terminals) abortive draw declaration.

    Validates the player's turn and kyuushu conditions, then processes the abortive draw.
    """
    if round_state.current_player_seat != seat:
        return ActionResult(
            [ErrorEvent(code="not_your_turn", message="not your turn", target=f"seat_{seat}")]
        )

    player = round_state.players[seat]
    if not can_call_kyuushu_kyuuhai(player, round_state):
        return ActionResult(
            [
                ErrorEvent(
                    code="cannot_call_kyuushu", message="cannot call kyuushu kyuuhai", target=f"seat_{seat}"
                )
            ]
        )

    result = call_kyuushu_kyuuhai(round_state)
    round_state.phase = RoundPhase.FINISHED
    process_abortive_draw(game_state, AbortiveDrawType.NINE_TERMINALS)

    events: list[GameEvent] = [RoundEndEvent(result=result, target="all")]
    return ActionResult(events)


def handle_pass(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> ActionResult:
    """
    Handle passing on a meld/ron opportunity.

    Pass is only valid when the current player has 13 tiles (just discarded).
    After acknowledging the pass, finalizes pending riichi if any,
    then advances the turn and draws for the next player.
    """
    events: list[GameEvent] = [PassAcknowledgedEvent(seat=seat, target=f"seat_{seat}")]

    # pass is only valid when a discard just happened (current player has 13 tiles)
    current_player = round_state.players[round_state.current_player_seat]
    if len(current_player.tiles) != HAND_SIZE_AFTER_DISCARD:
        # no pending call prompt, just acknowledge the pass
        return ActionResult(events)

    # finalize pending riichi if the discard was a riichi declaration
    if current_player.discards and current_player.discards[-1].is_riichi_discard:
        declare_riichi(current_player, game_state)
        events.append(RiichiDeclaredEvent(seat=round_state.current_player_seat, target="all"))

        # check for four riichi abortive draw
        if check_four_riichi(round_state):
            result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_RIICHI)
            round_state.phase = RoundPhase.FINISHED
            events.append(RoundEndEvent(result=result, target="all"))
            return ActionResult(events)

    # advance to the next player's turn
    advance_turn(round_state)

    # draw for next player
    if round_state.phase == RoundPhase.PLAYING:
        draw_events = process_draw_phase(round_state, game_state)
        events.extend(draw_events)

    return ActionResult(events)


def complete_added_kan_after_chankan_decline(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> list[GameEvent]:
    """
    Complete an added kan after chankan opportunity was declined.

    Called when all players pass on a chankan opportunity.
    Returns meld events and handles post-kan processing.
    """
    meld = call_added_kan(round_state, caller_seat, tile_id)
    tile_ids = list(meld.tiles) if meld.tiles else []

    events: list[GameEvent] = [
        MeldEvent(
            meld_type="kan",
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            tiles=[tile_to_string(t) for t in tile_ids],
            kan_type="added",
        )
    ]

    # check for four kans abortive draw
    if check_four_kans(round_state):
        result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_KANS)
        round_state.phase = RoundPhase.FINISHED
        events.append(RoundEndEvent(result=result, target="all"))
    else:
        # emit draw event for the dead wall tile
        player = round_state.players[caller_seat]
        if player.tiles:
            drawn_tile = player.tiles[-1]
            events.append(
                DrawEvent(
                    seat=caller_seat,
                    tile_id=drawn_tile,
                    tile=tile_to_string(drawn_tile),
                    target=f"seat_{caller_seat}",
                )
            )
        # emit turn event so the player knows their available actions
        if round_state.phase == RoundPhase.PLAYING:
            events.append(_create_turn_event(round_state, game_state, caller_seat))

    return events
