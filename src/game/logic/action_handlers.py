"""
Action handlers for game actions.

Each handler validates input and returns ActionResult containing events and optional new state.
These handlers are designed to be used by the MahjongGameService to process player actions.
"""

import logging

from game.logic.abortive import (
    call_kyuushu_kyuuhai,
    can_call_kyuushu_kyuuhai,
)
from game.logic.action_result import ActionResult, create_draw_event
from game.logic.call_resolution import resolve_call_prompt
from game.logic.enums import (
    CallType,
    GameAction,
    GameErrorCode,
    KanType,
    RoundPhase,
)
from game.logic.events import (
    ErrorEvent,
    EventType,
    GameEvent,
    RoundEndEvent,
)
from game.logic.exceptions import GameRuleError
from game.logic.state import (
    CallResponse,
    MahjongGameState,
    MahjongRoundState,
    PendingCallPrompt,
)
from game.logic.state_utils import (
    add_prompt_response,
    update_game_with_round,
    update_player,
)
from game.logic.turn import (
    process_discard_phase,
    process_meld_call,
    process_tsumo_call,
)
from game.logic.types import (
    ChiActionData,
    DiscardActionData,
    KanActionData,
    PonActionData,
    RiichiActionData,
)
from game.logic.win import apply_temporary_furiten

logger = logging.getLogger(__name__)


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


def _validate_call_prompt(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    tile_id: int,
    error_code: GameErrorCode,
) -> PendingCallPrompt | ActionResult:
    """Validate the pending call prompt for a meld call (pon, chi, etc.).

    Check that a pending call prompt exists, that the seat is among the pending
    callers, and that the tile_id matches the prompt's tile_id.

    Return the validated PendingCallPrompt on success, or an ActionResult with
    an ErrorEvent on failure.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning(f"invalid call from seat {seat}: no pending call prompt")
        return ActionResult(
            [
                ErrorEvent(
                    code=error_code,
                    message="no pending call prompt",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    if prompt.tile_id != tile_id:
        logger.warning(
            f"invalid call from seat {seat}: tile_id mismatch (expected={prompt.tile_id}, got={tile_id})"
        )
        return ActionResult(
            [
                ErrorEvent(
                    code=error_code,
                    message="tile_id mismatch",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    return prompt


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
    except GameRuleError as e:
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
    except GameRuleError as e:
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
    except GameRuleError as e:
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
    result = _validate_call_prompt(round_state, game_state, seat, data.tile_id, GameErrorCode.INVALID_PON)
    if isinstance(result, ActionResult):
        return result
    prompt = result

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
    result = _validate_call_prompt(round_state, game_state, seat, data.tile_id, GameErrorCode.INVALID_CHI)
    if isinstance(result, ActionResult):
        return result
    prompt = result

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
    except GameRuleError as e:
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

    # after kan, emit draw event for dead wall tile with available actions
    if new_round_state.phase == RoundPhase.PLAYING:
        player = new_round_state.players[seat]
        drawn_tile = player.tiles[-1] if player.tiles else None
        events.append(create_draw_event(new_round_state, new_game_state, seat, tile_id=drawn_tile))

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
    if not can_call_kyuushu_kyuuhai(player, round_state, game_state.settings):
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
