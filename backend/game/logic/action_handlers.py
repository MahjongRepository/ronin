import structlog

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
    MeldCallType,
    RoundPhase,
)
from game.logic.events import (
    ErrorEvent,
    EventType,
    GameEvent,
    RoundEndEvent,
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
    update_game_with_round,
    update_player,
)
from game.logic.tiles import TILES_PER_SUIT, is_honor, tile_to_34
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


def _create_error_result(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    seat: int,
    code: GameErrorCode,
    message: str,
) -> ActionResult:
    """
    Answer the acting seat with an ErrorEvent and leave the state unchanged.
    """
    return ActionResult(
        events=[ErrorEvent(code=code, message=message, target=f"seat_{seat}")],
        new_round_state=round_state,
        new_game_state=game_state,
    )


def _create_not_your_turn_error(
    round_state: MahjongRoundState, game_state: MahjongGameState, seat: int
) -> ActionResult:
    return _create_error_result(
        round_state, game_state, seat=seat, code=GameErrorCode.NOT_YOUR_TURN, message="not your turn"
    )


def _create_rule_error(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    error: GameRuleError,
) -> ActionResult:
    logger.info("action refused by a rule judgment", code=error.code.value, reason=str(error))
    return _create_error_result(round_state, game_state, seat=seat, code=error.code, message=str(error))


def _validate_call_prompt(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    tile_id: int,
    error_code: GameErrorCode,
) -> PendingCallPrompt | ActionResult:
    """
    Validate the pending call prompt for a meld call (pon, chi, etc.).

    Check that a pending call prompt exists, that the seat is among the pending callers, and that the tile_id matches
    the prompt's tile_id.

    Return the validated PendingCallPrompt on success, or an ActionResult with an ErrorEvent on failure.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning("invalid call: no pending call prompt", seat=seat)
        return ActionResult(
            [
                ErrorEvent(
                    code=error_code,
                    message="no pending call prompt",
                    target=f"seat_{seat}",
                ),
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    if prompt.tile_id != tile_id:
        logger.warning("invalid call: tile_id mismatch", seat=seat, expected=prompt.tile_id, got=tile_id)
        return ActionResult(
            [
                ErrorEvent(
                    code=error_code,
                    message="tile_id mismatch",
                    target=f"seat_{seat}",
                ),
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
    """
    Validate chi sequence_tiles before recording the response.

    Raises InvalidGameActionError if:
    - Either tile is not in the player's hand
    - The 3 tiles don't form a valid chi sequence (consecutive in same suit)
    - The sequence_tiles don't match, by tile type, one of the seat's chi options in the prompt

    The seat's chi meld is the one checked, also when the seat is offered pon too (pon sorts first); it exists because
    _validate_caller_action_matches_prompt ran upstream.
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
    is_same_suit = all_34[0] // TILES_PER_SUIT == all_34[2] // TILES_PER_SUIT
    if is_honor(all_34[0]) or not is_consecutive or not is_same_suit:
        raise InvalidGameActionError(
            action="call_chi",
            seat=seat,
            reason="tiles do not form a valid chi sequence",
        )

    chi_meld = next(m for m in prompt.caller(seat).melds if m.call_type == MeldCallType.CHI)
    submitted_34 = tuple(sorted(tile_to_34(t) for t in sequence_tiles))
    options = chi_meld.options or ()
    if not any(tuple(sorted(tile_to_34(t) for t in opt)) == submitted_34 for opt in options):
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
    """
    Validate that the player has enough matching tiles for a meld call.

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
    """
    Validate that the player's response action is among the calls the prompt offered the seat.

    A ron caller may only ron; a meld caller may make only one of its melds. Raises InvalidGameActionError otherwise.
    """
    caller = prompt.caller(seat)
    if caller.can_ron:
        if action != GameAction.CALL_RON:
            raise InvalidGameActionError(
                action=action.value,
                seat=seat,
                reason=f"only ron is valid for this seat on a {prompt.kind.value} prompt",
            )

        return

    if action == GameAction.CALL_RON:
        raise InvalidGameActionError(
            action=action.value,
            seat=seat,
            reason=f"cannot call ron on a {prompt.kind.value} prompt",
        )

    if action not in {_MELD_CALL_TYPE_TO_GAME_ACTION[m.call_type] for m in caller.melds}:
        available = ", ".join(m.call_type.value for m in caller.melds)
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


# --- Action Handlers ---


def handle_discard(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    seat: int,
    data: DiscardActionData,
) -> ActionResult:
    """
    Handle a discard action.

    Validates the player's turn and tile_id, then processes the discard. Returns ActionResult with events, post-discard
    flag, and new state; an illegal discard (kuikae, riichi tsumogiri) gets an ErrorEvent, a tile not in hand raises
    InvalidGameActionError.
    """
    if not _is_turn_of(round_state, seat):
        return _create_not_your_turn_error(round_state, game_state, seat)

    try:
        new_round_state, new_game_state, events = process_discard_phase(
            round_state,
            game_state,
            data.tile_id,
            is_riichi=False,
        )
    except ImpossibleActionError as e:
        raise InvalidGameActionError(action="discard", seat=seat, reason=str(e)) from e
    except GameRuleError as e:
        return _create_rule_error(round_state, game_state, seat, e)

    return ActionResult(
        events,
        needs_post_discard=True,
        new_round_state=new_round_state,
        new_game_state=new_game_state,
    )


def handle_riichi(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    seat: int,
    data: RiichiActionData,
) -> ActionResult:
    """
    Handle a riichi declaration with discard.

    Validates the player's turn and tile_id, then processes the riichi discard. Returns ActionResult with events and new
    state; a discard that breaks tenpai or is not legal gets an ErrorEvent, riichi not offered or a tile not in hand
    raises InvalidGameActionError.
    """
    if not _is_turn_of(round_state, seat):
        return _create_not_your_turn_error(round_state, game_state, seat)

    try:
        new_round_state, new_game_state, events = process_discard_phase(
            round_state,
            game_state,
            data.tile_id,
            is_riichi=True,
        )
    except ImpossibleActionError as e:
        raise InvalidGameActionError(action="declare_riichi", seat=seat, reason=str(e)) from e
    except GameRuleError as e:
        return _create_rule_error(round_state, game_state, seat, e)

    return ActionResult(
        events,
        needs_post_discard=True,
        new_round_state=new_round_state,
        new_game_state=new_game_state,
    )


def handle_tsumo(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    seat: int,
) -> ActionResult:
    """
    Handle a tsumo declaration.

    Validates the player's turn and processes the tsumo win. Returns ActionResult with events and new state.
    """
    if not _is_turn_of(round_state, seat):
        return _create_not_your_turn_error(round_state, game_state, seat)

    try:
        new_round_state, new_game_state, events = process_tsumo_call(round_state, game_state, winner_seat=seat)
    except ImpossibleActionError as e:
        raise InvalidGameActionError(action="declare_tsumo", seat=seat, reason=str(e)) from e

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def handle_ron(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    seat: int,
) -> ActionResult:
    """
    Handle a ron call from a player.

    Record ron intent on the pending call prompt. Execute during resolution (supports double ron). Returns ActionResult
    with events and new state.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning("invalid ron: no pending call prompt", seat=seat)
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_RON,
                    message="no pending call prompt",
                    target=f"seat_{seat}",
                ),
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    # validate ron is allowed on this prompt type
    _validate_caller_action_matches_prompt(prompt, seat=seat, action=GameAction.CALL_RON)

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_RON)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        return resolve_call_prompt(new_round_state, new_game_state)

    return ActionResult(
        [],
        new_round_state=new_round_state,
        new_game_state=new_game_state,
    )  # waiting for other callers


def handle_pon(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    seat: int,
    data: PonActionData,
) -> ActionResult:
    """
    Handle a pon call from a player.

    Record pon intent on the pending call prompt. Execute the pon only during resolution when all callers respond.
    Returns ActionResult with events and new state.
    """
    result = _validate_call_prompt(
        round_state, game_state, seat=seat, tile_id=data.tile_id, error_code=GameErrorCode.INVALID_PON
    )
    if isinstance(result, ActionResult):
        return result

    prompt = result

    # validate caller action matches prompt
    _validate_caller_action_matches_prompt(prompt, seat=seat, action=GameAction.CALL_PON)

    # validate matching tiles exist
    player = round_state.players[seat]
    _validate_matching_tile_count(player, tile_id=prompt.tile_id, seat=seat, min_count=2, action_name="call_pon")

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_PON)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        return resolve_call_prompt(new_round_state, new_game_state)

    return ActionResult(
        [],
        new_round_state=new_round_state,
        new_game_state=new_game_state,
    )  # waiting for other callers


def handle_chi(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    seat: int,
    data: ChiActionData,
) -> ActionResult:
    """
    Handle a chi call from a player.

    Record chi intent on the pending call prompt. Execute the chi only during resolution when all callers respond.
    Returns ActionResult with events and new state.
    """
    result = _validate_call_prompt(
        round_state, game_state, seat=seat, tile_id=data.tile_id, error_code=GameErrorCode.INVALID_CHI
    )
    if isinstance(result, ActionResult):
        return result

    prompt = result

    # validate caller action matches prompt
    _validate_caller_action_matches_prompt(prompt, seat=seat, action=GameAction.CALL_CHI)

    # validate sequence_tiles before recording response
    player = round_state.players[seat]
    _validate_chi_sequence(player, prompt, seat=seat, tile_id=data.tile_id, sequence_tiles=data.sequence_tiles)

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_CHI, sequence_tiles=data.sequence_tiles)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        return resolve_call_prompt(new_round_state, new_game_state)

    return ActionResult(
        [],
        new_round_state=new_round_state,
        new_game_state=new_game_state,
    )  # waiting for other callers


def _handle_open_kan_call_response(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    submitted_tile_id: int,
) -> ActionResult:
    """
    Handle open kan as a call response to a pending prompt.

    Record intent and trigger resolution when all callers have responded. Returns ActionResult with events and new
    state.
    """
    result = _validate_call_prompt(
        round_state,
        game_state,
        seat=seat,
        tile_id=submitted_tile_id,
        error_code=GameErrorCode.INVALID_KAN,
    )
    if isinstance(result, ActionResult):
        return result

    prompt = result

    # validate caller action matches prompt
    _validate_caller_action_matches_prompt(prompt, seat=seat, action=GameAction.CALL_KAN)

    # validate open kan: tile count
    player = round_state.players[seat]
    _validate_matching_tile_count(player, tile_id=prompt.tile_id, seat=seat, min_count=3, action_name="call_kan")

    # add response
    response = CallResponse(seat=seat, action=GameAction.CALL_KAN)
    new_prompt = add_prompt_response(prompt, response)
    new_round_state = round_state.model_copy(update={"pending_call_prompt": new_prompt})
    new_game_state = update_game_with_round(game_state, new_round_state)

    if not new_prompt.pending_seats:
        return resolve_call_prompt(new_round_state, new_game_state)

    return ActionResult(
        [],
        new_round_state=new_round_state,
        new_game_state=new_game_state,
    )  # waiting for other callers


def _handle_self_kan(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    seat: int,
    data: KanActionData,
) -> ActionResult:
    """
    Handle closed or added kan during the player's own turn.

    Executes the kan immediately via process_meld_call, then checks for chankan prompt or emits a draw event for the
    dead wall replacement tile.
    """
    # after pon/chi, the player must discard — kan requires a drawn tile
    if round_state.is_after_meld_call:
        raise InvalidGameActionError(
            action="call_kan",
            seat=seat,
            reason="cannot declare kan after a meld call (must discard first)",
        )

    try:
        meld_call_type = data.kan_type.to_meld_call_type()
        meld_input = MeldCallInput(caller_seat=seat, call_type=meld_call_type, tile_id=data.tile_id)
        new_round_state, new_game_state, events = process_meld_call(
            round_state,
            game_state,
            meld_input=meld_input,
        )
    except ImpossibleActionError as e:
        raise InvalidGameActionError(action="call_kan", seat=seat, reason=str(e)) from e

    if new_round_state.phase == RoundPhase.FINISHED:
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    # check for chankan prompt (added kan may be robbed)
    has_chankan_prompt = any(
        e.type == EventType.CALL_PROMPT and getattr(e, "call_type", None) == CallType.CHANKAN for e in events
    )
    if has_chankan_prompt:
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    # after kan, emit draw event for dead wall tile with available actions
    if new_round_state.phase == RoundPhase.PLAYING:
        player = new_round_state.players[seat]
        drawn_tile = player.tiles[-1]
        events = [*events, create_draw_event(new_round_state, new_game_state, seat=seat, tile_id=drawn_tile)]

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def handle_kan(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    seat: int,
    data: KanActionData,
) -> ActionResult:
    """
    Handle a kan call (open, closed, or added).

    Open kan as call response: record intent on pending prompt.
    Closed/added kan during own turn: execute immediately.
    Returns ActionResult with events and new state.
    """
    # Open kan is a call response to another player's discard (validated by _validate_call_prompt)
    if data.kan_type == KanType.OPEN:
        return _handle_open_kan_call_response(round_state, game_state, seat=seat, submitted_tile_id=data.tile_id)

    # closed/added kan during own turn - immediate execution
    if not _is_turn_of(round_state, seat):
        return _create_not_your_turn_error(round_state, game_state, seat)

    return _handle_self_kan(round_state, game_state, seat=seat, data=data)


def handle_kyuushu(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    *,
    seat: int,
) -> ActionResult:
    """
    Handle kyuushu kyuuhai (nine terminals) abortive draw declaration.

    Validates the player's turn and kyuushu conditions, then processes the abortive draw. Returns ActionResult with
    events and new state.
    """
    if not _is_turn_of(round_state, seat):
        return _create_not_your_turn_error(round_state, game_state, seat)

    player = round_state.players[seat]
    if not can_call_kyuushu_kyuuhai(player, round_state, settings=game_state.settings):
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
    *,
    seat: int,
) -> ActionResult:
    """
    Handle passing on a meld/ron opportunity.

    Record the pass on the pending call prompt and apply furiten if applicable. When all callers have responded, trigger
    resolution. Returns ActionResult with events and new state.
    """
    events: list[GameEvent] = []
    new_round_state = round_state
    new_game_state = game_state

    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning("invalid pass: no pending call prompt", seat=seat)
        return ActionResult(
            [
                ErrorEvent(
                    code=GameErrorCode.INVALID_PASS,
                    message="no pending call prompt",
                    target=f"seat_{seat}",
                ),
            ],
            new_round_state=round_state,
            new_game_state=game_state,
        )

    # apply furiten for passing on ron/chankan opportunity
    if prompt.caller(seat).can_ron:
        new_round_state = apply_temporary_furiten(new_round_state, seat)
        player = new_round_state.players[seat]
        if player.is_riichi:
            new_round_state = update_player(new_round_state, seat, is_riichi_furiten=True)

        new_game_state = update_game_with_round(new_game_state, new_round_state)

    # Remove from pending without recording a CallResponse. resolve_call_prompt
    # treats absence from responses as a pass; only actionable responses (ron, pon,
    # chi, kan) are recorded, keeping responses sparse for priority resolution.
    pending = set(prompt.pending_seats)
    pending.remove(seat)
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
