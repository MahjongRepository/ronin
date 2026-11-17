import structlog

from game.logic.abortive import (
    call_kyuushu_kyuuhai,
    can_call_kyuushu_kyuuhai,
)
from game.logic.action_result import ActionResult
from game.logic.call_resolution import resolve_call_prompt
from game.logic.decision import CallAnswer, Chi, Discard, Kan, Pon, Riichi, Ron
from game.logic.enums import (
    KanType,
    MeldCallType,
)
from game.logic.exceptions import GameRuleError, ImpossibleActionError
from game.logic.refusal import Refusal, RefusalCode, RefusalKind
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
from game.logic.types import MeldCallInput
from game.logic.win import apply_temporary_furiten

logger = structlog.get_logger()


def _is_turn_of(round_state: MahjongRoundState, seat: int) -> bool:
    """
    Check that the seat may take a turn action now: it is the current player and no call prompt is pending.

    A turn action during a pending prompt is a race the client cannot see (another seat's call window is still open), so
    it gets the same answer as a turn action out of turn.
    """
    return round_state.current_player_seat == seat and round_state.pending_call_prompt is None


_NOT_YOUR_TURN = Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.SEAT_NOT_AWAITED)


def _refuse_by_rule(error: GameRuleError) -> Refusal:
    logger.info("action refused by a rule judgment", code=error.code.value, reason=str(error))
    return Refusal(kind=RefusalKind.RULE, code=error.code)


def _refuse_as_not_offered(code: RefusalCode, reason: str) -> Refusal:
    logger.info("action refused as not offered", code=code.value, reason=reason)
    return Refusal(kind=RefusalKind.NOT_OFFERED, code=code)


def _refuse_impossible(error: ImpossibleActionError) -> Refusal:
    return _refuse_as_not_offered(error.code, str(error))


def _refuse_unanswerable_call(prompt: PendingCallPrompt | None, seat: int) -> Refusal:
    """
    Refuse a call answer, or a pass, from a seat no prompt waits on: already answered when it is one of the prompt's
    callers, else not awaited.
    """
    answered = prompt is not None and any(caller.seat == seat for caller in prompt.callers)
    code = RefusalCode.ALREADY_ANSWERED if answered else RefusalCode.SEAT_NOT_AWAITED
    return Refusal(kind=RefusalKind.NOT_AWAITED, code=code)


def _validate_call_prompt(
    round_state: MahjongRoundState,
    *,
    seat: int,
    answer: CallAnswer,
) -> PendingCallPrompt | Refusal:
    """
    Validate a call response (ron, pon, chi or open kan) against the pending call prompt, before any call's own checks.

    Refuse as not awaited when no prompt waits on the seat, and as not offered when an open kan names a tile of another
    type than the prompt's (the other answers name no called tile) or the prompt did not offer the seat this call. A
    pass needs neither check.

    Return the validated PendingCallPrompt on success, or a Refusal on failure.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None or seat not in prompt.pending_seats:
        logger.warning("invalid call: no pending call prompt", seat=seat)
        return _refuse_unanswerable_call(prompt, seat)

    if isinstance(answer, Kan) and tile_to_34(answer.tile) != tile_to_34(prompt.tile_id):
        return _refuse_as_not_offered(RefusalCode.NOT_OFFERED, f"open kan tile {answer.tile} is not the call's type")

    refusal = _check_caller_action_matches_prompt(prompt, seat=seat, answer=answer)
    return refusal if refusal is not None else prompt


def _check_chi_sequence(
    player: MahjongPlayer,
    prompt: PendingCallPrompt,
    seat: int,
    sequence_tiles: tuple[int, int],
) -> Refusal | None:
    """
    Check chi sequence_tiles before recording the response; return a Refusal when they do not hold, else None.

    Refuses if:
    - Either tile is not in the player's hand
    - The sequence_tiles don't match, by tile type, one of the seat's chi options in the prompt (each option is a run
      with the prompt's tile)

    The seat's chi meld is the one checked, also when the seat is offered pon too (pon sorts first); it exists because
    _validate_call_prompt ran upstream.
    """
    hand_list = list(player.tiles)
    for t in sequence_tiles:
        if t not in hand_list:
            return _refuse_as_not_offered(RefusalCode.TILE_NOT_HELD, f"sequence tile {t} not in hand")

        hand_list.remove(t)

    chi_meld = next(m for m in prompt.caller(seat).melds if m.call_type == MeldCallType.CHI)
    submitted_34 = tuple(sorted(tile_to_34(t) for t in sequence_tiles))
    options = chi_meld.options or ()
    if not any(tuple(sorted(tile_to_34(t) for t in opt)) == submitted_34 for opt in options):
        return _refuse_as_not_offered(RefusalCode.NOT_OFFERED, "sequence tiles not among available options")

    return None


def _resolve_pon_tiles(
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
    seat: int,
    tiles: tuple[int, int] | None,
) -> tuple[int, int] | Refusal:
    """
    Return the two hand tiles a pon takes, or a Refusal when the named tiles do not hold.

    No tiles take the seat's first offered pair. Named tiles must be two distinct held copies of the prompt's tile type:
    the pon offers a pair for every look the hand holds, so any such pair matches an offered one.
    """
    if tiles is None:
        pon_meld = next(m for m in prompt.caller(seat).melds if m.call_type == MeldCallType.PON)
        return next(iter(pon_meld.options or ()))

    hand = game_state.round_state.players[seat].tiles
    if tiles[0] == tiles[1] or any(t not in hand for t in tiles):
        return _refuse_as_not_offered(RefusalCode.TILE_NOT_HELD, f"pon tiles {tiles} not held")

    if any(tile_to_34(t) != tile_to_34(prompt.tile_id) for t in tiles):
        return _refuse_as_not_offered(RefusalCode.NOT_OFFERED, "pon tiles not of the called tile's type")

    return tiles


def _check_caller_action_matches_prompt(
    prompt: PendingCallPrompt,
    seat: int,
    answer: CallAnswer,
) -> Refusal | None:
    """
    Check that the player's response action is among the calls the prompt offered the seat; return a Refusal when it is
    not, else None.

    The offered calls are the seat's ron and its melds.
    """
    caller = prompt.caller(seat)
    ron: list[type[CallAnswer]] = [Ron] if caller.can_ron else []
    offered = [*ron, *(_MELD_CALL_TYPE_TO_ANSWER[m.call_type] for m in caller.melds)]
    if type(answer) in offered:
        return None

    available = ", ".join(_ANSWER_NAMES[a] for a in offered)
    name = _ANSWER_NAMES[type(answer)]
    return _refuse_as_not_offered(
        RefusalCode.NOT_OFFERED, f"action {name} does not match available call types: {available}"
    )


_MELD_CALL_TYPE_TO_ANSWER: dict[MeldCallType, type[CallAnswer]] = {
    MeldCallType.PON: Pon,
    MeldCallType.CHI: Chi,
    MeldCallType.OPEN_KAN: Kan,
}

_ANSWER_NAMES: dict[type[CallAnswer], str] = {Ron: "call_ron", Pon: "call_pon", Chi: "call_chi", Kan: "call_kan"}


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
    if not isinstance(response.action, Ron) and prompt.caller(response.seat).can_ron:
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
    action: Discard,
) -> ActionResult | Refusal:
    """
    Handle a discard action.

    Validates the player's turn and tile_id, then processes the discard. Returns ActionResult with events and new state;
    an illegal discard (kuikae, riichi tsumogiri) is refused by rule, a tile not in hand as not offered.
    """
    if not _is_turn_of(game_state.round_state, seat):
        return _NOT_YOUR_TURN

    try:
        new_game_state, events = process_discard_phase(game_state, action.tile, is_riichi=False)
    except ImpossibleActionError as e:
        return _refuse_impossible(e)
    except GameRuleError as e:
        return _refuse_by_rule(e)

    return ActionResult(events, state=new_game_state)


def handle_riichi(
    game_state: MahjongGameState,
    *,
    seat: int,
    action: Riichi,
) -> ActionResult | Refusal:
    """
    Handle a riichi declaration with discard.

    Validates the player's turn and tile_id, then processes the riichi discard. Returns ActionResult with events and new
    state; a discard that breaks tenpai or is not legal is refused by rule, riichi not offered or a tile not in hand as
    not offered.
    """
    if not _is_turn_of(game_state.round_state, seat):
        return _NOT_YOUR_TURN

    try:
        new_game_state, events = process_discard_phase(game_state, action.tile, is_riichi=True)
    except ImpossibleActionError as e:
        return _refuse_impossible(e)
    except GameRuleError as e:
        return _refuse_by_rule(e)

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
        return _refuse_impossible(e)

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
    result = _validate_call_prompt(game_state.round_state, seat=seat, answer=Ron())
    if isinstance(result, Refusal):
        return result

    return _record_call_response(game_state, result, CallResponse(seat=seat, action=Ron()))


def handle_pon(
    game_state: MahjongGameState,
    *,
    seat: int,
    action: Pon,
) -> ActionResult | Refusal:
    """
    Handle a pon call from a player.

    Record pon intent, with the hand tiles it takes, on the pending call prompt. Execute the pon only during resolution
    when all callers respond. Returns ActionResult with events and new state.
    """
    result = _validate_call_prompt(game_state.round_state, seat=seat, answer=action)
    if isinstance(result, Refusal):
        return result

    tiles = _resolve_pon_tiles(game_state, result, seat=seat, tiles=action.tiles)
    if isinstance(tiles, Refusal):
        return tiles

    return _record_call_response(game_state, result, CallResponse(seat=seat, action=Pon(tiles=tiles)))


def handle_chi(
    game_state: MahjongGameState,
    *,
    seat: int,
    action: Chi,
) -> ActionResult | Refusal:
    """
    Handle a chi call from a player.

    Record chi intent on the pending call prompt. Execute the chi only during resolution when all callers respond.
    Returns ActionResult with events and new state.
    """
    round_state = game_state.round_state
    result = _validate_call_prompt(round_state, seat=seat, answer=action)
    if isinstance(result, Refusal):
        return result

    refusal = _check_chi_sequence(round_state.players[seat], result, seat=seat, sequence_tiles=action.tiles)
    if refusal is not None:
        return refusal

    return _record_call_response(game_state, result, CallResponse(seat=seat, action=action))


def _handle_open_kan_call_response(
    game_state: MahjongGameState,
    seat: int,
    action: Kan,
) -> ActionResult | Refusal:
    """
    Handle open kan as a call response to a pending prompt.

    Record intent and trigger resolution when all callers have responded. Returns ActionResult with events and new
    state.
    """
    result = _validate_call_prompt(game_state.round_state, seat=seat, answer=action)
    if isinstance(result, Refusal):
        return result

    return _record_call_response(game_state, result, CallResponse(seat=seat, action=action))


def _handle_self_kan(
    game_state: MahjongGameState,
    seat: int,
    action: Kan,
) -> ActionResult | Refusal:
    """
    Handle closed or added kan during the player's own turn.

    Executes the kan immediately via process_meld_call, with its rinshan draw, unless it opened a chankan prompt (the
    kan then waits for the robbers' answers).
    """
    if game_state.round_state.is_after_meld_call:
        return _refuse_as_not_offered(
            RefusalCode.NOT_OFFERED, "cannot declare kan after a meld call (must discard first)"
        )

    try:
        meld_call_type = action.kan_type.to_meld_call_type()
        meld_input = MeldCallInput(caller_seat=seat, call_type=meld_call_type, tile_id=action.tile)
        new_game_state, events = process_meld_call(game_state, meld_input=meld_input)
    except ImpossibleActionError as e:
        return _refuse_impossible(e)

    return ActionResult(events, state=new_game_state)


def handle_kan(
    game_state: MahjongGameState,
    *,
    seat: int,
    action: Kan,
) -> ActionResult | Refusal:
    """
    Handle a kan call (open, closed, or added).

    Open kan as call response: record intent on pending prompt.
    Closed/added kan during own turn: execute immediately.
    Returns ActionResult with events and new state.
    """
    # Open kan is a call response to another player's discard (validated by _validate_call_prompt)
    if action.kan_type == KanType.OPEN:
        return _handle_open_kan_call_response(game_state, seat=seat, action=action)

    # closed/added kan during own turn - immediate execution
    if not _is_turn_of(game_state.round_state, seat):
        return _NOT_YOUR_TURN

    return _handle_self_kan(game_state, seat=seat, action=action)


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
        return _refuse_as_not_offered(RefusalCode.NOT_OFFERED, "kyuushu kyuuhai conditions not met")

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
        return _refuse_unanswerable_call(prompt, seat)

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
