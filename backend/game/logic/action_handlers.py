import structlog

from game.logic.abortive import (
    call_kyuushu_kyuuhai,
    can_call_kyuushu_kyuuhai,
)
from game.logic.action_result import ActionResult, Refusal
from game.logic.call_resolution import resolve_call_prompt
from game.logic.enums import (
    GameAction,
    GameErrorCode,
    KanType,
    MeldCallType,
)
from game.logic.exceptions import GameRuleError, ImpossibleActionError, InvalidGameActionError
from game.logic.state import (
    CallResponse,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    PendingCallPrompt,
)
from game.logic.state_utils import (
    add_prompt_response,
    finish_round,
    update_game_with_round,
    update_player,
)
from game.logic.tiles import tile_to_34
from game.logic.turn import (
    process_discard_phase,
    process_meld_call,
    process_tsumo_call,
)
from game.logic.types import (
    ChiActionData,
    DiscardActionData,
    KanActionData,
    MeldCallInput,
    PonActionData,
    RiichiActionData,
)
from game.logic.win import apply_temporary_furiten

logger = structlog.get_logger()


def _is_turn_of(round_state: MahjongRoundState, seat: int) -> bool:
    """
    Check that the seat may take a turn action now: it is the current player and no call prompt is pending.

    A turn action during a pending prompt is a race the client cannot see (another seat's call window is still open), so
    it gets the same answer as a turn action out of turn.
    """
    return round_state.current_player_seat == seat and round_state.pending_call_prompt is None


_NOT_YOUR_TURN = Refusal(code=GameErrorCode.NOT_YOUR_TURN, message="not your turn")


def _create_rule_refusal(error: GameRuleError) -> Refusal:
    logger.info("action refused by a rule judgment", code=error.code.value, reason=str(error))
    return Refusal(code=error.code, message=str(error))


def _validate_call_prompt(
    round_state: MahjongRoundState,
    *,
    seat: int,
    action: GameAction,
    tile_id: int | None,
    error_code: GameErrorCode,
) -> PendingCallPrompt | Refusal:
    """
    Validate a call response (ron, pon, chi or open kan) against the pending call prompt, before any call's own checks.

    Refuse when no prompt waits on the seat or the tile_id is not the prompt's (a ron sends none); raise
    InvalidGameActionError when the prompt did not offer the seat this call. A pass needs neither check.

    Return the validated PendingCallPrompt on success, or a Refusal on failure.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning("invalid call: no pending call prompt", seat=seat)
        return Refusal(code=error_code, message="no pending call prompt")

    if tile_id is not None and prompt.tile_id != tile_id:
        logger.warning("invalid call: tile_id mismatch", seat=seat, expected=prompt.tile_id, got=tile_id)
        return Refusal(code=error_code, message="tile_id mismatch")

    _validate_caller_action_matches_prompt(prompt, seat=seat, action=action)
    return prompt


def _validate_chi_sequence(
    player: MahjongPlayer,
    prompt: PendingCallPrompt,
    seat: int,
    sequence_tiles: tuple[int, int],
) -> None:
    """
    Validate chi sequence_tiles before recording the response.

    Raises InvalidGameActionError if:
    - Either tile is not in the player's hand
    - The sequence_tiles don't match, by tile type, one of the seat's chi options in the prompt (each option is a run
      with the prompt's tile)

    The seat's chi meld is the one checked, also when the seat is offered pon too (pon sorts first); it exists because
    _validate_call_prompt ran upstream.
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

    chi_meld = next(m for m in prompt.caller(seat).melds if m.call_type == MeldCallType.CHI)
    submitted_34 = tuple(sorted(tile_to_34(t) for t in sequence_tiles))
    options = chi_meld.options or ()
    if not any(tuple(sorted(tile_to_34(t) for t in opt)) == submitted_34 for opt in options):
        raise InvalidGameActionError(
            action="call_chi",
            seat=seat,
            reason="sequence tiles not among available options",
        )


def _validate_caller_action_matches_prompt(
    prompt: PendingCallPrompt,
    seat: int,
    action: GameAction,
) -> None:
    """
    Validate that the player's response action is among the calls the prompt offered the seat.

    The offered calls are the seat's ron and its melds. Raises InvalidGameActionError otherwise.
    """
    caller = prompt.caller(seat)
    ron = [GameAction.CALL_RON] if caller.can_ron else []
    offered = [*ron, *(_MELD_CALL_TYPE_TO_GAME_ACTION[m.call_type] for m in caller.melds)]
    if action not in offered:
        available = ", ".join(a.value for a in offered)
        raise InvalidGameActionError(
            action=action.value,
            seat=seat,
            reason=f"action {action.value} does not match available call types: {available}",
        )


_MELD_CALL_TYPE_TO_GAME_ACTION: dict[MeldCallType, GameAction] = {
    MeldCallType.PON: GameAction.CALL_PON,
    MeldCallType.CHI: GameAction.CALL_CHI,
    MeldCallType.OPEN_KAN: GameAction.CALL_KAN,
}


def _decline_ron(round_state: MahjongRoundState, seat: int) -> MahjongRoundState:
    """
    Make a seat that declined its ron (or chankan) temporarily furiten, and riichi furiten for good when in riichi.
    """
    new_round_state = apply_temporary_furiten(round_state, seat)
    if new_round_state.players[seat].is_riichi:
        new_round_state = update_player(new_round_state, seat, is_riichi_furiten=True)

    return new_round_state


# --- Action Handlers ---


def _record_call_response(
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
    response: CallResponse,
) -> ActionResult:
    """
    Record a validated call response on the pending prompt, and resolve the prompt once no seat is pending.

    A meld from a seat that could ron declines the ron, with the furiten a pass would bring.
    """
    round_state = game_state.round_state
    if response.action != GameAction.CALL_RON and prompt.caller(response.seat).can_ron:
        round_state = _decline_ron(round_state, response.seat)

    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        return resolve_call_prompt(new_game_state)

    return ActionResult([], state=new_game_state)


def handle_discard(
    game_state: MahjongGameState,
    *,
    seat: int,
    data: DiscardActionData,
) -> ActionResult | Refusal:
    """
    Handle a discard action.

    Validates the player's turn and tile_id, then processes the discard. Returns ActionResult with events and new state;
    an illegal discard (kuikae, riichi tsumogiri) is refused, a tile not in hand raises InvalidGameActionError.
    """
    if not _is_turn_of(game_state.round_state, seat):
        return _NOT_YOUR_TURN

    try:
        new_game_state, events = process_discard_phase(game_state, data.tile_id, is_riichi=False)
    except ImpossibleActionError as e:
        raise InvalidGameActionError(action="discard", seat=seat, reason=str(e)) from e
    except GameRuleError as e:
        return _create_rule_refusal(e)

    return ActionResult(events, state=new_game_state)


def handle_riichi(
    game_state: MahjongGameState,
    *,
    seat: int,
    data: RiichiActionData,
) -> ActionResult | Refusal:
    """
    Handle a riichi declaration with discard.

    Validates the player's turn and tile_id, then processes the riichi discard. Returns ActionResult with events and new
    state; a discard that breaks tenpai or is not legal is refused, riichi not offered or a tile not in hand raises
    InvalidGameActionError.
    """
    if not _is_turn_of(game_state.round_state, seat):
        return _NOT_YOUR_TURN

    try:
        new_game_state, events = process_discard_phase(game_state, data.tile_id, is_riichi=True)
    except ImpossibleActionError as e:
        raise InvalidGameActionError(action="declare_riichi", seat=seat, reason=str(e)) from e
    except GameRuleError as e:
        return _create_rule_refusal(e)

    return ActionResult(events, state=new_game_state)


def handle_tsumo(
    game_state: MahjongGameState,
    *,
    seat: int,
) -> ActionResult | Refusal:
    """
    Handle a tsumo declaration.

    Validates the player's turn and processes the tsumo win. Returns ActionResult with events and new state.
    """
    if not _is_turn_of(game_state.round_state, seat):
        return _NOT_YOUR_TURN

    try:
        new_game_state, events = process_tsumo_call(game_state, winner_seat=seat)
    except ImpossibleActionError as e:
        raise InvalidGameActionError(action="declare_tsumo", seat=seat, reason=str(e)) from e

    return ActionResult(events, state=new_game_state)


def handle_ron(
    game_state: MahjongGameState,
    *,
    seat: int,
) -> ActionResult | Refusal:
    """
    Handle a ron call from a player.

    Record ron intent on the pending call prompt. Execute during resolution (supports double ron). Returns ActionResult
    with events and new state.
    """
    result = _validate_call_prompt(
        game_state.round_state,
        seat=seat,
        action=GameAction.CALL_RON,
        tile_id=None,
        error_code=GameErrorCode.INVALID_RON,
    )
    if isinstance(result, Refusal):
        return result

    return _record_call_response(game_state, result, CallResponse(seat=seat, action=GameAction.CALL_RON))


def handle_pon(
    game_state: MahjongGameState,
    *,
    seat: int,
    data: PonActionData,
) -> ActionResult | Refusal:
    """
    Handle a pon call from a player.

    Record pon intent on the pending call prompt. Execute the pon only during resolution when all callers respond.
    Returns ActionResult with events and new state.
    """
    result = _validate_call_prompt(
        game_state.round_state,
        seat=seat,
        action=GameAction.CALL_PON,
        tile_id=data.tile_id,
        error_code=GameErrorCode.INVALID_PON,
    )
    if isinstance(result, Refusal):
        return result

    return _record_call_response(game_state, result, CallResponse(seat=seat, action=GameAction.CALL_PON))


def handle_chi(
    game_state: MahjongGameState,
    *,
    seat: int,
    data: ChiActionData,
) -> ActionResult | Refusal:
    """
    Handle a chi call from a player.

    Record chi intent on the pending call prompt. Execute the chi only during resolution when all callers respond.
    Returns ActionResult with events and new state.
    """
    round_state = game_state.round_state
    result = _validate_call_prompt(
        round_state,
        seat=seat,
        action=GameAction.CALL_CHI,
        tile_id=data.tile_id,
        error_code=GameErrorCode.INVALID_CHI,
    )
    if isinstance(result, Refusal):
        return result

    prompt = result

    # validate sequence_tiles before recording response
    player = round_state.players[seat]
    _validate_chi_sequence(player, prompt, seat=seat, sequence_tiles=data.sequence_tiles)

    response = CallResponse(seat=seat, action=GameAction.CALL_CHI, sequence_tiles=data.sequence_tiles)
    return _record_call_response(game_state, prompt, response)


def _handle_open_kan_call_response(
    game_state: MahjongGameState,
    seat: int,
    submitted_tile_id: int,
) -> ActionResult | Refusal:
    """
    Handle open kan as a call response to a pending prompt.

    Record intent and trigger resolution when all callers have responded. Returns ActionResult with events and new
    state.
    """
    result = _validate_call_prompt(
        game_state.round_state,
        seat=seat,
        action=GameAction.CALL_KAN,
        tile_id=submitted_tile_id,
        error_code=GameErrorCode.INVALID_KAN,
    )
    if isinstance(result, Refusal):
        return result

    return _record_call_response(game_state, result, CallResponse(seat=seat, action=GameAction.CALL_KAN))


def _handle_self_kan(
    game_state: MahjongGameState,
    seat: int,
    data: KanActionData,
) -> ActionResult | Refusal:
    """
    Handle closed or added kan during the player's own turn.

    Executes the kan immediately via process_meld_call, with its rinshan draw, unless it opened a chankan prompt (the
    kan then waits for the robbers' answers).
    """
    # after pon/chi, the player must discard — kan requires a drawn tile
    if game_state.round_state.is_after_meld_call:
        raise InvalidGameActionError(
            action="call_kan",
            seat=seat,
            reason="cannot declare kan after a meld call (must discard first)",
        )

    try:
        meld_call_type = data.kan_type.to_meld_call_type()
        meld_input = MeldCallInput(caller_seat=seat, call_type=meld_call_type, tile_id=data.tile_id)
        new_game_state, events = process_meld_call(game_state, meld_input=meld_input)
    except ImpossibleActionError as e:
        raise InvalidGameActionError(action="call_kan", seat=seat, reason=str(e)) from e

    return ActionResult(events, state=new_game_state)


def handle_kan(
    game_state: MahjongGameState,
    *,
    seat: int,
    data: KanActionData,
) -> ActionResult | Refusal:
    """
    Handle a kan call (open, closed, or added).

    Open kan as call response: record intent on pending prompt.
    Closed/added kan during own turn: execute immediately.
    Returns ActionResult with events and new state.
    """
    # Open kan is a call response to another player's discard (validated by _validate_call_prompt)
    if data.kan_type == KanType.OPEN:
        return _handle_open_kan_call_response(game_state, seat=seat, submitted_tile_id=data.tile_id)

    # closed/added kan during own turn - immediate execution
    if not _is_turn_of(game_state.round_state, seat):
        return _NOT_YOUR_TURN

    return _handle_self_kan(game_state, seat=seat, data=data)


def handle_kyuushu(
    game_state: MahjongGameState,
    *,
    seat: int,
) -> ActionResult | Refusal:
    """
    Handle kyuushu kyuuhai (nine terminals) abortive draw declaration.

    Validates the player's turn and kyuushu conditions, then processes the abortive draw. Returns ActionResult with
    events and new state.
    """
    round_state = game_state.round_state
    if not _is_turn_of(round_state, seat):
        return _NOT_YOUR_TURN

    player = round_state.players[seat]
    if not can_call_kyuushu_kyuuhai(player, round_state, settings=game_state.settings):
        raise InvalidGameActionError(
            action="call_kyuushu",
            seat=seat,
            reason="kyuushu kyuuhai conditions not met",
        )

    new_round_state, result = call_kyuushu_kyuuhai(round_state)
    new_game_state, round_end = finish_round(update_game_with_round(game_state, new_round_state), result)
    return ActionResult([round_end], state=new_game_state)


def handle_pass(
    game_state: MahjongGameState,
    *,
    seat: int,
) -> ActionResult | Refusal:
    """
    Handle passing on a meld/ron opportunity.

    Record the pass on the pending call prompt and apply furiten if applicable. When all callers have responded, trigger
    resolution. Returns ActionResult with events and new state.
    """
    new_round_state = game_state.round_state
    prompt = new_round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning("invalid pass: no pending call prompt", seat=seat)
        return Refusal(code=GameErrorCode.INVALID_PASS, message="no pending call prompt")

    if prompt.caller(seat).can_ron:
        new_round_state = _decline_ron(new_round_state, seat)

    # Remove from pending without recording a CallResponse. resolve_call_prompt
    # treats absence from responses as a pass; only actionable responses (ron, pon,
    # chi, kan) are recorded, keeping responses sparse for priority resolution.
    pending = set(prompt.pending_seats)
    pending.remove(seat)
    new_prompt = prompt.model_copy(update={"pending_seats": frozenset(pending)})
    new_round_state = new_round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    # resolve if all callers have responded
    if not new_prompt.pending_seats:
        return resolve_call_prompt(new_game_state)

    return ActionResult([], state=new_game_state)
