"""
Action handlers for game actions.

Each handler validates input and returns ActionResult containing events and optional new state.
These handlers are designed to be used by the MahjongGameService to process player actions.
"""

import logging
from typing import NamedTuple

from game.logic.abortive import (
    AbortiveDrawType,
    call_kyuushu_kyuuhai,
    can_call_kyuushu_kyuuhai,
    check_four_kans,
    check_four_riichi,
    process_abortive_draw,
)
from game.logic.actions import get_available_actions
from game.logic.enums import (
    MELD_CALL_PRIORITY,
    CallType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldCallType,
    MeldViewType,
    RoundPhase,
)
from game.logic.melds import call_added_kan
from game.logic.riichi import declare_riichi
from game.logic.state import (
    CallResponse,
    MahjongGameState,
    MahjongRoundState,
    PendingCallPrompt,
)
from game.logic.state_utils import (
    add_prompt_response,
    advance_turn,
    clear_pending_prompt,
    update_game_with_round,
    update_player,
)
from game.logic.turn import (
    emit_deferred_dora_events,
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
    process_tsumo_call,
)
from game.logic.types import (
    ChiActionData,
    DiscardActionData,
    KanActionData,
    MeldCaller,
    PonActionData,
    RiichiActionData,
)
from game.logic.win import apply_temporary_furiten
from game.messaging.events import (
    DrawEvent,
    ErrorEvent,
    EventType,
    GameEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    TurnEvent,
)

logger = logging.getLogger(__name__)

# number of ron callers for triple ron abortive draw
TRIPLE_RON_COUNT = 3


class ActionResult(NamedTuple):
    """
    Result of an action handler execution.

    Contains the events produced by the action and optionally the new
    immutable state after the action. When new_round_state and new_game_state
    are provided, the caller should use them to update its stored state.
    """

    events: list[GameEvent]
    needs_post_discard: bool = False
    new_round_state: MahjongRoundState | None = None
    new_game_state: MahjongGameState | None = None


def _create_not_your_turn_error(
    seat: int,
    round_state: MahjongRoundState | None = None,
    game_state: MahjongGameState | None = None,
) -> ActionResult:
    """Create an error result for when it's not a player's turn."""
    return ActionResult(
        events=[ErrorEvent(code=GameErrorCode.NOT_YOUR_TURN, message="not your turn", target=f"seat_{seat}")],
        new_round_state=round_state,
        new_game_state=game_state,
    )


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


def _action_to_meld_call_type(action: GameAction) -> MeldCallType:
    """Convert a GameAction to MeldCallType."""
    mapping = {
        GameAction.CALL_PON: MeldCallType.PON,
        GameAction.CALL_CHI: MeldCallType.CHI,
        GameAction.CALL_KAN: MeldCallType.OPEN_KAN,
    }
    return mapping[action]


def _pick_best_meld_response(
    meld_responses: list[CallResponse],
    prompt: PendingCallPrompt,
) -> CallResponse | None:
    """
    Pick the highest-priority meld response.

    Use the caller priority from the original prompt to determine winner.
    Priority is based on the actual response action, not the best available option.
    Priority order: kan(0) > pon(1) > chi(2).
    Tie-break: counter-clockwise distance from discarder (closer = higher priority).
    """
    # build (seat, call_type) -> priority map from original callers
    caller_priority: dict[tuple[int, MeldCallType], int] = {}
    for caller in prompt.callers:
        if isinstance(caller, MeldCaller):
            caller_priority[(caller.seat, caller.call_type)] = MELD_CALL_PRIORITY.get(caller.call_type, 99)

    def sort_key(response: CallResponse) -> tuple[int, int]:
        call_type = _action_to_meld_call_type(response.action)
        priority = caller_priority.get((response.seat, call_type), 99)
        distance = (response.seat - prompt.from_seat) % 4
        return (priority, distance)

    best: CallResponse | None = None
    best_key: tuple[int, int] = (999, 999)
    for response in meld_responses:
        key = sort_key(response)
        if key < best_key:
            best = response
            best_key = key
    return best


def _resolve_ron_responses(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
    ron_responses: list[CallResponse],
) -> ActionResult:
    """Resolve ron responses from the pending call prompt."""
    # sort by position in prompt.callers (counter-clockwise from discarder)
    caller_order = {(c if isinstance(c, int) else c.seat): i for i, c in enumerate(prompt.callers)}
    ron_responses = sorted(ron_responses, key=lambda r: caller_order.get(r.seat, 999))

    # triple ron - abortive draw (all three opponents declared ron)
    if len(ron_responses) == TRIPLE_RON_COUNT:
        result = process_abortive_draw(game_state, AbortiveDrawType.TRIPLE_RON)
        new_round_state = clear_pending_prompt(round_state)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = update_game_with_round(game_state, new_round_state)
        events: list[GameEvent] = [RoundEndEvent(result=result, target="all")]
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    # double ron or single ron
    ron_seats = [r.seat for r in ron_responses]
    is_chankan = prompt.call_type == CallType.CHANKAN
    new_round_state, new_game_state, events = process_ron_call(
        round_state, game_state, ron_seats, prompt.tile_id, prompt.from_seat, is_chankan=is_chankan
    )
    new_round_state = clear_pending_prompt(new_round_state)
    new_game_state = update_game_with_round(new_game_state, new_round_state)
    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def _resolve_meld_response(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
    best: CallResponse,
) -> ActionResult:
    """Resolve the winning meld response from the pending call prompt."""
    meld_type = _action_to_meld_call_type(best.action)
    new_round_state, new_game_state, events = process_meld_call(
        round_state,
        game_state,
        best.seat,
        meld_type,
        prompt.tile_id,
        sequence_tiles=best.sequence_tiles,
    )
    new_round_state = clear_pending_prompt(new_round_state)
    new_game_state = update_game_with_round(new_game_state, new_round_state)

    if new_round_state.phase == RoundPhase.FINISHED:
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    # open kan draws from dead wall; emit DrawEvent so client knows the drawn tile
    if meld_type == MeldCallType.OPEN_KAN:
        player = new_round_state.players[best.seat]
        if player.tiles:
            drawn_tile = player.tiles[-1]
            events.append(
                DrawEvent(
                    seat=best.seat,
                    tile_id=drawn_tile,
                    target=f"seat_{best.seat}",
                )
            )

    events.append(_create_turn_event(new_round_state, new_game_state, best.seat))
    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def _resolve_all_passed(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
) -> ActionResult:
    """
    Handle resolution when all callers passed.

    Reveal deferred dora (if ron prompt was declined), finalize pending riichi,
    check four riichi abortive draw, advance turn, and draw for next player.
    """
    events: list[GameEvent] = []
    new_round_state = round_state
    new_game_state = game_state

    # reveal deferred dora now that the discard passed the ron check
    new_round_state, dora_events = emit_deferred_dora_events(new_round_state)
    events.extend(dora_events)
    new_game_state = update_game_with_round(new_game_state, new_round_state)

    discarder = new_round_state.players[prompt.from_seat]
    if discarder.discards and discarder.discards[-1].is_riichi_discard and not discarder.is_riichi:
        new_round_state, new_game_state = declare_riichi(new_round_state, new_game_state, prompt.from_seat)
        events.append(RiichiDeclaredEvent(seat=prompt.from_seat, target="all"))

        if check_four_riichi(new_round_state):
            result = process_abortive_draw(new_game_state, AbortiveDrawType.FOUR_RIICHI)
            new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
            new_game_state = update_game_with_round(new_game_state, new_round_state)
            events.append(RoundEndEvent(result=result, target="all"))
            return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    new_round_state = advance_turn(new_round_state)
    new_game_state = update_game_with_round(new_game_state, new_round_state)

    if new_round_state.phase == RoundPhase.PLAYING:
        new_round_state, new_game_state, draw_events = process_draw_phase(new_round_state, new_game_state)
        events.extend(draw_events)

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def complete_added_kan_after_chankan_decline(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Complete an added kan after chankan opportunity was declined.

    Called when all players pass on a chankan opportunity.
    Furiten is applied per-caller in handle_pass before resolution.
    Returns (new_round_state, new_game_state, events).
    """
    new_round_state, meld = call_added_kan(round_state, caller_seat, tile_id)
    new_game_state = update_game_with_round(game_state, new_round_state)
    tile_ids = list(meld.tiles) if meld.tiles else []

    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            kan_type=KanType.ADDED,
        )
    ]

    # check for four kans abortive draw
    if check_four_kans(new_round_state):
        result = process_abortive_draw(new_game_state, AbortiveDrawType.FOUR_KANS)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = update_game_with_round(new_game_state, new_round_state)
        events.append(RoundEndEvent(result=result, target="all"))
    else:
        # emit draw event for the dead wall tile
        player = new_round_state.players[caller_seat]
        if player.tiles:
            drawn_tile = player.tiles[-1]
            events.append(
                DrawEvent(
                    seat=caller_seat,
                    tile_id=drawn_tile,
                    target=f"seat_{caller_seat}",
                )
            )
        # emit turn event so the player knows their available actions
        if new_round_state.phase == RoundPhase.PLAYING:
            events.append(_create_turn_event(new_round_state, new_game_state, caller_seat))

    return new_round_state, new_game_state, events


def resolve_call_prompt(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
) -> ActionResult:
    """
    Resolve pending call prompt after all callers have responded.

    Pick the winning response by priority (ron > pon/kan > chi > all pass)
    and execute it. Clear the pending prompt.
    Returns ActionResult with events and new state.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None:
        return ActionResult([], new_round_state=round_state, new_game_state=game_state)

    ron_responses = [r for r in prompt.responses if r.action == GameAction.CALL_RON]
    meld_responses = [
        r
        for r in prompt.responses
        if r.action in (GameAction.CALL_PON, GameAction.CALL_CHI, GameAction.CALL_KAN)
    ]

    # priority 1: ron
    if ron_responses:
        return _resolve_ron_responses(round_state, game_state, prompt, ron_responses)

    # priority 2: meld (pon/kan > chi, determined by caller priority in prompt)
    if meld_responses:
        best = _pick_best_meld_response(meld_responses, prompt)
        if best is not None:
            return _resolve_meld_response(round_state, game_state, prompt, best)

    # all passed
    new_round_state = clear_pending_prompt(round_state)
    new_game_state = update_game_with_round(game_state, new_round_state)

    if prompt.call_type == CallType.CHANKAN:
        new_round_state, new_game_state, events = complete_added_kan_after_chankan_decline(
            new_round_state,
            new_game_state,
            prompt.from_seat,
            prompt.tile_id,
        )
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    return _resolve_all_passed(new_round_state, new_game_state, prompt)


# --- Action Handlers ---


def handle_discard(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: DiscardActionData,
) -> ActionResult:
    """
    Handle a discard action.

    Validates the player's turn and tile_id, then processes the discard.
    Returns ActionResult with events, post-discard flag, and new state.
    """
    if round_state.current_player_seat != seat:
        return _create_not_your_turn_error(seat, round_state, game_state)

    try:
        new_round_state, new_game_state, events = process_discard_phase(
            round_state, game_state, data.tile_id, is_riichi=False
        )
        return ActionResult(
            events,
            needs_post_discard=True,
            new_round_state=new_round_state,
            new_game_state=new_game_state,
        )
    except ValueError as e:
        logger.warning(f"invalid discard from seat {seat}: {e}")
        return ActionResult(
            [ErrorEvent(code=GameErrorCode.INVALID_DISCARD, message=str(e), target=f"seat_{seat}")],
            new_round_state=round_state,
            new_game_state=game_state,
        )


def handle_riichi(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: RiichiActionData,
) -> ActionResult:
    """
    Handle a riichi declaration with discard.

    Validates the player's turn and tile_id, then processes the riichi discard.
    Returns ActionResult with events and new state.
    """
    if round_state.current_player_seat != seat:
        return _create_not_your_turn_error(seat, round_state, game_state)

    try:
        new_round_state, new_game_state, events = process_discard_phase(
            round_state, game_state, data.tile_id, is_riichi=True
        )
        return ActionResult(
            events,
            needs_post_discard=True,
            new_round_state=new_round_state,
            new_game_state=new_game_state,
        )
    except ValueError as e:
        logger.warning(f"invalid riichi from seat {seat}: {e}")
        return ActionResult(
            [ErrorEvent(code=GameErrorCode.INVALID_RIICHI, message=str(e), target=f"seat_{seat}")],
            new_round_state=round_state,
            new_game_state=game_state,
        )


def handle_tsumo(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> ActionResult:
    """
    Handle a tsumo declaration.

    Validates the player's turn and processes the tsumo win.
    Returns ActionResult with events and new state.
    """
    if round_state.current_player_seat != seat:
        return _create_not_your_turn_error(seat, round_state, game_state)

    try:
        new_round_state, new_game_state, events = process_tsumo_call(round_state, game_state, seat)
        return ActionResult(
            events,
            new_round_state=new_round_state,
            new_game_state=new_game_state,
        )
    except ValueError as e:
        logger.warning(f"invalid tsumo from seat {seat}: {e}")
        return ActionResult(
            [ErrorEvent(code=GameErrorCode.INVALID_TSUMO, message=str(e), target=f"seat_{seat}")],
            new_round_state=round_state,
            new_game_state=game_state,
        )


def handle_ron(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> ActionResult:
    """
    Handle a ron call from a player.

    Record ron intent on the pending call prompt.
    Execute during resolution (supports double ron).
    Returns ActionResult with events and new state.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning(f"invalid ron from seat {seat}: no pending call prompt")
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_RON,
                    message="no pending call prompt",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_RON)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        resolve_result = resolve_call_prompt(new_round_state, new_game_state)
        return ActionResult(
            resolve_result.events,
            new_round_state=resolve_result.new_round_state,
            new_game_state=resolve_result.new_game_state,
        )

    return ActionResult(
        [], new_round_state=new_round_state, new_game_state=new_game_state
    )  # waiting for other callers


def handle_pon(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: PonActionData,
) -> ActionResult:
    """
    Handle a pon call from a player.

    Record pon intent on the pending call prompt.
    Execute the pon only during resolution when all callers respond.
    Returns ActionResult with events and new state.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning(f"invalid pon from seat {seat}: no pending call prompt")
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_PON,
                    message="no pending call prompt",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    if prompt.tile_id != data.tile_id:
        logger.warning(
            f"invalid pon from seat {seat}: tile_id mismatch (expected={prompt.tile_id}, got={data.tile_id})"
        )
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_PON,
                    message="tile_id mismatch",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_PON)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        resolve_result = resolve_call_prompt(new_round_state, new_game_state)
        return ActionResult(
            resolve_result.events,
            new_round_state=resolve_result.new_round_state,
            new_game_state=resolve_result.new_game_state,
        )

    return ActionResult(
        [], new_round_state=new_round_state, new_game_state=new_game_state
    )  # waiting for other callers


def handle_chi(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: ChiActionData,
) -> ActionResult:
    """
    Handle a chi call from a player.

    Record chi intent on the pending call prompt.
    Execute the chi only during resolution when all callers respond.
    Returns ActionResult with events and new state.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning(f"invalid chi from seat {seat}: no pending call prompt")
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_CHI,
                    message="no pending call prompt",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    if prompt.tile_id != data.tile_id:
        logger.warning(
            f"invalid chi from seat {seat}: tile_id mismatch (expected={prompt.tile_id}, got={data.tile_id})"
        )
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_CHI,
                    message="tile_id mismatch",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_CHI, sequence_tiles=data.sequence_tiles)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        resolve_result = resolve_call_prompt(new_round_state, new_game_state)
        return ActionResult(
            resolve_result.events,
            new_round_state=resolve_result.new_round_state,
            new_game_state=resolve_result.new_game_state,
        )

    return ActionResult(
        [], new_round_state=new_round_state, new_game_state=new_game_state
    )  # waiting for other callers


def _handle_open_kan_call_response(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> ActionResult:
    """
    Handle open kan as a call response to a pending prompt.

    Record intent and trigger resolution when all callers have responded.
    Returns ActionResult with events and new state.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning(f"invalid open kan from seat {seat}: not a pending caller")
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_KAN,
                    message="not a pending caller",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_KAN)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        resolve_result = resolve_call_prompt(new_round_state, new_game_state)
        return ActionResult(
            resolve_result.events,
            new_round_state=resolve_result.new_round_state,
            new_game_state=resolve_result.new_game_state,
        )

    return ActionResult(
        [], new_round_state=new_round_state, new_game_state=new_game_state
    )  # waiting for other callers


def handle_kan(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: KanActionData,
) -> ActionResult:
    """
    Handle a kan call (open, closed, or added).

    Open kan as call response: record intent on pending prompt.
    Closed/added kan during own turn: execute immediately.
    Returns ActionResult with events and new state.
    """
    # open kan as call response uses pending prompt
    if data.kan_type == KanType.OPEN and round_state.pending_call_prompt is not None:
        return _handle_open_kan_call_response(round_state, game_state, seat)

    # closed/added kan during own turn - immediate execution
    if round_state.current_player_seat != seat:
        return _create_not_your_turn_error(seat, round_state, game_state)

    try:
        meld_call_type = data.kan_type.to_meld_call_type()
        new_round_state, new_game_state, events = process_meld_call(
            round_state, game_state, seat, meld_call_type, data.tile_id
        )
    except ValueError as e:
        logger.warning(f"invalid kan from seat {seat}: {e}")
        return ActionResult(
            [ErrorEvent(code=GameErrorCode.INVALID_KAN, message=str(e), target=f"seat_{seat}")],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    if new_round_state.phase == RoundPhase.FINISHED:
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    # check for chankan prompt
    has_chankan_prompt = any(
        e.type == EventType.CALL_PROMPT and getattr(e, "call_type", None) == CallType.CHANKAN for e in events
    )
    if has_chankan_prompt:
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    # after kan, emit draw event for dead wall tile, then turn event
    if new_round_state.phase == RoundPhase.PLAYING:
        player = new_round_state.players[seat]
        if player.tiles:
            drawn_tile = player.tiles[-1]
            events.append(
                DrawEvent(
                    seat=seat,
                    tile_id=drawn_tile,
                    target=f"seat_{seat}",
                )
            )
        events.append(_create_turn_event(new_round_state, new_game_state, seat))

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def handle_kyuushu(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> ActionResult:
    """
    Handle kyuushu kyuuhai (nine terminals) abortive draw declaration.

    Validates the player's turn and kyuushu conditions, then processes the abortive draw.
    Returns ActionResult with events and new state.
    """
    if round_state.current_player_seat != seat:
        return _create_not_your_turn_error(seat, round_state, game_state)

    player = round_state.players[seat]
    if not can_call_kyuushu_kyuuhai(player, round_state):
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.CANNOT_CALL_KYUUSHU,
                    message="cannot call kyuushu kyuuhai",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    new_round_state, result = call_kyuushu_kyuuhai(round_state)
    new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
    new_game_state = update_game_with_round(game_state, new_round_state)

    events: list[GameEvent] = [RoundEndEvent(result=result, target="all")]
    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def handle_pass(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
) -> ActionResult:
    """
    Handle passing on a meld/ron opportunity.

    Record the pass on the pending call prompt and apply furiten if applicable.
    When all callers have responded, trigger resolution.
    Returns ActionResult with events and new state.
    """
    events: list[GameEvent] = []
    new_round_state = round_state
    new_game_state = game_state

    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning(f"invalid pass from seat {seat}: no pending call prompt")
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_PASS,
                    message="no pending call prompt",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    # apply furiten for passing on ron/chankan opportunity
    if prompt.call_type in (CallType.RON, CallType.CHANKAN):
        new_round_state = apply_temporary_furiten(new_round_state, seat)
        player = new_round_state.players[seat]
        if player.is_riichi:
            new_round_state = update_player(new_round_state, seat, is_riichi_furiten=True)
        new_game_state = update_game_with_round(new_game_state, new_round_state)

    # record pass and remove from pending (update the prompt)
    pending = set(prompt.pending_seats)
    pending.discard(seat)
    new_prompt = prompt.model_copy(update={"pending_seats": frozenset(pending)})
    new_round_state = new_round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(new_game_state, new_round_state)

    # resolve if all callers have responded
    if not new_prompt.pending_seats:
        resolve_result = resolve_call_prompt(new_round_state, new_game_state)
        events.extend(resolve_result.events)
        new_round_state = resolve_result.new_round_state
        new_game_state = resolve_result.new_game_state

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)
