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
from game.logic.call_resolution import _pick_best_meld_response, resolve_call_prompt
from game.logic.enums import (
    CallType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldCallType,
    RoundPhase,
)
from game.logic.events import (
    ErrorEvent,
    EventType,
    GameEvent,
    RoundEndEvent,
)
from game.logic.exceptions import GameRuleError, InvalidGameActionError
from game.logic.state import (
    CallResponse,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    PendingCallPrompt,
)
from game.logic.state_utils import (
    add_prompt_response,
    update_game_with_round,
    update_player,
)
from game.logic.tiles import is_honor, tile_to_34
from game.logic.turn import (
    process_discard_phase,
    process_meld_call,
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

logger = logging.getLogger(__name__)

# Actions that require it to be the player's turn (not a call response)
TURN_ACTIONS = frozenset(
    {
        GameAction.DISCARD,
        GameAction.DECLARE_RIICHI,
        GameAction.DECLARE_TSUMO,
        GameAction.CALL_KYUUSHU,
    }
)


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


def _validate_chi_sequence(
    player: MahjongPlayer,
    prompt: PendingCallPrompt,
    seat: int,
    tile_id: int,
    sequence_tiles: tuple[int, int],
) -> None:
    """Validate chi sequence_tiles before recording the response.

    Raises InvalidGameActionError if:
    - Either tile is not in the player's hand
    - The 3 tiles don't form a valid chi sequence (consecutive in same suit)
    - The sequence_tiles don't match one of the available chi options in the prompt
    """
    # Both tiles must be in the player's hand
    hand_list = list(player.tiles)
    for t in sequence_tiles:
        if t not in hand_list:
            raise InvalidGameActionError(
                action="call_chi",
                seat=seat,
                reason=f"sequence tile {t} not in hand",
            )
        hand_list.remove(t)

    # The 3 tiles must form a valid sequence (consecutive values in same suit, not honor)
    all_34 = sorted(tile_to_34(t) for t in (*sequence_tiles, tile_id))
    is_consecutive = all_34[1] == all_34[0] + 1 and all_34[2] == all_34[0] + 2
    is_same_suit = all_34[0] // 9 == all_34[2] // 9
    if is_honor(all_34[0]) or not is_consecutive or not is_same_suit:
        raise InvalidGameActionError(
            action="call_chi",
            seat=seat,
            reason="tiles do not form a valid chi sequence",
        )

    # sequence_tiles must match one of the available options (by tile type, not exact ID)
    # Caller metadata existence is enforced by _validate_caller_action_matches_prompt upstream
    caller_info = next(
        (c for c in prompt.callers if isinstance(c, MeldCaller) and c.seat == seat),
        None,
    )
    if caller_info is not None and caller_info.options:
        submitted_34 = tuple(sorted(tile_to_34(t) for t in sequence_tiles))
        if not any(tuple(sorted(tile_to_34(t) for t in opt)) == submitted_34 for opt in caller_info.options):
            raise InvalidGameActionError(
                action="call_chi",
                seat=seat,
                reason="sequence tiles not among available options",
            )


def _validate_matching_tile_count(
    player: MahjongPlayer,
    tile_id: int,
    seat: int,
    min_count: int,
    action_name: str,
) -> None:
    """Validate that the player has enough matching tiles for a meld call.

    Raises InvalidGameActionError if the player has fewer than min_count matching tiles.
    """
    tile_34 = tile_to_34(tile_id)
    matching = sum(1 for t in player.tiles if tile_to_34(t) == tile_34)
    if matching < min_count:
        raise InvalidGameActionError(
            action=action_name,
            seat=seat,
            reason=f"not enough matching tiles for {action_name} (need {min_count}, have {matching})",
        )


def _validate_caller_action_matches_prompt(
    prompt: PendingCallPrompt,
    seat: int,
    action: GameAction,
) -> None:
    """Validate that the player's response action is among their available call types.

    Raises InvalidGameActionError if:
    - The player sends CALL_RON on a MELD prompt (ron not available on meld prompts)
    - The player's action doesn't match any of their available call types in the prompt
    """
    # For RON/CHANKAN prompts, only CALL_RON (and PASS, handled elsewhere) is valid
    if prompt.call_type in (CallType.RON, CallType.CHANKAN):
        if action != GameAction.CALL_RON:
            raise InvalidGameActionError(
                action=action.value,
                seat=seat,
                reason=f"only ron is valid on a {prompt.call_type.value} prompt",
            )
        return

    # For meld prompts, check action matches available call types
    if prompt.call_type != CallType.MELD:
        raise InvalidGameActionError(
            action=action.value,
            seat=seat,
            reason=f"unknown prompt type: {prompt.call_type.value}",
        )

    # Ron is never valid on a meld-only prompt
    if action == GameAction.CALL_RON:
        raise InvalidGameActionError(
            action=action.value,
            seat=seat,
            reason="cannot call ron on a meld prompt",
        )
    # Collect all caller entries for this seat (a player can have multiple, e.g. both pon and kan)
    seat_callers = [c for c in prompt.callers if isinstance(c, MeldCaller) and c.seat == seat]
    if not seat_callers:
        # Seat is pending but has no caller metadata -- inconsistent prompt state
        raise InvalidGameActionError(
            action=action.value,
            seat=seat,
            reason="seat is pending but not present in callers metadata",
        )
    all_allowed: frozenset[GameAction] = frozenset().union(
        *(_MELD_CALL_TYPE_TO_GAME_ACTIONS.get(c.call_type, frozenset()) for c in seat_callers)
    )
    if action not in all_allowed:
        available = ", ".join(c.call_type.value for c in seat_callers)
        raise InvalidGameActionError(
            action=action.value,
            seat=seat,
            reason=f"action {action.value} does not match available call types: {available}",
        )


def _find_offending_seat_from_prompt(prompt: PendingCallPrompt, fallback_seat: int) -> int:
    """Identify the winning caller's seat from prompt responses for error attribution.

    When resolution fails, the error is from the response being executed (ron > pon/kan > chi),
    not from the player whose response happened to trigger resolution.
    Uses the same priority logic as resolve_call_prompt: ron callers sorted by caller order,
    meld callers picked by _pick_best_meld_response (kan > pon > chi, distance tie-break).
    """
    ron_responses = [r for r in prompt.responses if r.action == GameAction.CALL_RON]
    if ron_responses:
        # Sort by caller order (counter-clockwise from discarder), same as _resolve_ron_responses
        caller_order = {(c if isinstance(c, int) else c.seat): i for i, c in enumerate(prompt.callers)}
        ron_responses = sorted(ron_responses, key=lambda r: caller_order.get(r.seat, 999))
        return ron_responses[0].seat
    meld_responses = [
        r
        for r in prompt.responses
        if r.action in (GameAction.CALL_PON, GameAction.CALL_CHI, GameAction.CALL_KAN)
    ]
    if meld_responses:
        best = _pick_best_meld_response(meld_responses, prompt)
        if best is not None:
            return best.seat
    return fallback_seat


def _resolve_call_prompt_safe(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
    triggering_seat: int,
) -> ActionResult:
    """Resolve a call prompt with a safety net for resolution-time exceptions.

    Wraps resolve_call_prompt to catch GameRuleError and convert to InvalidGameActionError
    with correct blame attribution (the offending caller, not the triggering respondent).
    """
    try:
        resolve_result = resolve_call_prompt(round_state, game_state)
    except GameRuleError as e:
        offending_seat = _find_offending_seat_from_prompt(prompt, triggering_seat)
        raise InvalidGameActionError(action="resolve_call", seat=offending_seat, reason=str(e)) from e
    return ActionResult(
        resolve_result.events,
        new_round_state=resolve_result.new_round_state,
        new_game_state=resolve_result.new_game_state,
    )


_MELD_CALL_TYPE_TO_GAME_ACTIONS: dict[MeldCallType, frozenset[GameAction]] = {
    MeldCallType.PON: frozenset({GameAction.CALL_PON}),
    MeldCallType.CHI: frozenset({GameAction.CALL_CHI}),
    MeldCallType.OPEN_KAN: frozenset({GameAction.CALL_KAN}),
}


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
        raise InvalidGameActionError(action="discard", seat=seat, reason=str(e)) from e


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
        raise InvalidGameActionError(action="declare_riichi", seat=seat, reason=str(e)) from e


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
        raise InvalidGameActionError(action="declare_tsumo", seat=seat, reason=str(e)) from e


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

    # validate ron is allowed on this prompt type
    _validate_caller_action_matches_prompt(prompt, seat, GameAction.CALL_RON)

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_RON)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        return _resolve_call_prompt_safe(new_round_state, new_game_state, new_prompt, seat)

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

    # validate caller action matches prompt
    _validate_caller_action_matches_prompt(prompt, seat, GameAction.CALL_PON)

    # validate matching tiles exist
    player = round_state.players[seat]
    _validate_matching_tile_count(player, prompt.tile_id, seat, min_count=2, action_name="call_pon")

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_PON)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        return _resolve_call_prompt_safe(new_round_state, new_game_state, new_prompt, seat)

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

    # validate caller action matches prompt
    _validate_caller_action_matches_prompt(prompt, seat, GameAction.CALL_CHI)

    # validate sequence_tiles before recording response
    player = round_state.players[seat]
    _validate_chi_sequence(player, prompt, seat, data.tile_id, data.sequence_tiles)

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_CHI, sequence_tiles=data.sequence_tiles)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        return _resolve_call_prompt_safe(new_round_state, new_game_state, new_prompt, seat)

    return ActionResult(
        [], new_round_state=new_round_state, new_game_state=new_game_state
    )  # waiting for other callers


def _handle_open_kan_call_response(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    submitted_tile_id: int,
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

    # tile_id mismatch is a race condition (prompt resolved and recreated) -> soft error
    if prompt.tile_id != submitted_tile_id:
        logger.warning(
            f"invalid open kan from seat {seat}: tile_id mismatch "
            f"(expected={prompt.tile_id}, got={submitted_tile_id})"
        )
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_KAN,
                    message="tile_id mismatch",
                    target=f"seat_{seat}",
                )
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    # validate caller action matches prompt
    _validate_caller_action_matches_prompt(prompt, seat, GameAction.CALL_KAN)

    # validate open kan: tile count
    player = round_state.players[seat]
    _validate_matching_tile_count(player, prompt.tile_id, seat, min_count=3, action_name="call_kan")

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_KAN)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        return _resolve_call_prompt_safe(new_round_state, new_game_state, new_prompt, seat)

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
    # open kan requires a pending prompt - open kan is a call response to another player's
    # discard and cannot be self-initiated, so no pending prompt means fabricated data
    if data.kan_type == KanType.OPEN:
        if round_state.pending_call_prompt is None:
            raise InvalidGameActionError(
                action="call_kan",
                seat=seat,
                reason="open kan requires a pending call prompt",
            )
        return _handle_open_kan_call_response(round_state, game_state, seat, data.tile_id)

    # closed/added kan cannot be called while a call prompt is pending
    if round_state.pending_call_prompt is not None:
        raise InvalidGameActionError(
            action="call_kan",
            seat=seat,
            reason=f"cannot call {data.kan_type.value} kan while a call prompt is pending",
        )

    # closed/added kan during own turn - immediate execution
    if round_state.current_player_seat != seat:
        return _create_not_your_turn_error(seat, round_state, game_state)

    try:
        meld_call_type = data.kan_type.to_meld_call_type()
        new_round_state, new_game_state, events = process_meld_call(
            round_state, game_state, seat, meld_call_type, data.tile_id
        )
    except GameRuleError as e:
        raise InvalidGameActionError(action="call_kan", seat=seat, reason=str(e)) from e

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

    if not game_state.settings.has_kyuushu_kyuuhai:
        raise InvalidGameActionError(
            action="call_kyuushu",
            seat=seat,
            reason="kyuushu kyuuhai is disabled by game settings",
        )

    player = round_state.players[seat]
    if not can_call_kyuushu_kyuuhai(player, round_state, game_state.settings):
        raise InvalidGameActionError(
            action="call_kyuushu",
            seat=seat,
            reason="kyuushu kyuuhai conditions not met",
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
        resolve_result = _resolve_call_prompt_safe(new_round_state, new_game_state, new_prompt, seat)
        events.extend(resolve_result.events)
        new_round_state = resolve_result.new_round_state
        new_game_state = resolve_result.new_game_state

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)
