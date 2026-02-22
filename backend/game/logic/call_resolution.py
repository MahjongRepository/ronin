"""Call resolution subsystem -- resolve pending call prompts after all callers respond.

Handles ron resolution, meld resolution, all-passed flow, and chankan decline
completion. Extracted from action_handlers.py to give the call-resolution state
machine its own module and test surface.
"""

from typing import TYPE_CHECKING

import structlog

from game.logic.abortive import (
    AbortiveDrawType,
    check_four_kans,
    check_four_riichi,
    process_abortive_draw,
)
from game.logic.action_result import ActionResult, create_draw_event
from game.logic.enums import (
    FALLBACK_MELD_PRIORITY,
    MELD_CALL_PRIORITY,
    CallType,
    GameAction,
    MeldCallType,
    MeldViewType,
    RoundPhase,
)
from game.logic.events import (
    GameEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
)
from game.logic.melds import call_added_kan
from game.logic.riichi import declare_riichi
from game.logic.settings import NUM_PLAYERS
from game.logic.state_utils import (
    advance_turn,
    clear_pending_prompt,
    update_game_with_round,
)
from game.logic.turn import (
    _maybe_emit_dora_event,
    emit_deferred_dora_events,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
)
from game.logic.types import MeldCaller, MeldCallInput, RonCallInput

if TYPE_CHECKING:
    from game.logic.state import (
        CallResponse,
        MahjongGameState,
        MahjongRoundState,
        PendingCallPrompt,
    )

logger = structlog.get_logger()

FALLBACK_CALLER_ORDER = 999  # sorts unknown seats after all known ones


_ACTION_TO_MELD_CALL_TYPE = {
    GameAction.CALL_PON: MeldCallType.PON,
    GameAction.CALL_CHI: MeldCallType.CHI,
    GameAction.CALL_KAN: MeldCallType.OPEN_KAN,
}


def _action_to_meld_call_type(action: GameAction) -> MeldCallType:
    """Convert a GameAction to MeldCallType."""
    result = _ACTION_TO_MELD_CALL_TYPE.get(action)
    if result is None:
        raise ValueError(f"no meld call type for action: {action}")
    return result


def pick_best_meld_response(
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
            caller_priority[(caller.seat, caller.call_type)] = MELD_CALL_PRIORITY.get(
                caller.call_type,
                FALLBACK_MELD_PRIORITY,
            )

    # in DISCARD prompts, ron callers (int entries) may pass on ron and fall
    # back to a meld action. Their MeldCaller was stripped by the ron-dominant
    # policy, so accept meld responses from any seat listed in prompt.callers.
    ron_caller_seats = {c for c in prompt.callers if isinstance(c, int)}

    # filter to responses from recognized callers only
    valid_responses: list[CallResponse] = []
    for response in meld_responses:
        call_type = _action_to_meld_call_type(response.action)
        if (response.seat, call_type) in caller_priority:
            valid_responses.append(response)
        elif response.seat in ron_caller_seats:
            # ron caller falling back to meld: derive priority from action
            caller_priority[(response.seat, call_type)] = MELD_CALL_PRIORITY.get(call_type, FALLBACK_MELD_PRIORITY)
            valid_responses.append(response)
        else:
            logger.warning(
                "ignoring meld response: not in original callers",
                response_seat=response.seat,
                action=response.action,
            )

    def sort_key(response: CallResponse) -> tuple[int, int]:
        call_type = _action_to_meld_call_type(response.action)
        priority = caller_priority[(response.seat, call_type)]
        distance = (response.seat - prompt.from_seat) % NUM_PLAYERS
        return (priority, distance)

    best: CallResponse | None = None
    best_key: tuple[int, int] = (FALLBACK_CALLER_ORDER, FALLBACK_CALLER_ORDER)
    for response in valid_responses:
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
    ron_responses = sorted(ron_responses, key=lambda r: caller_order.get(r.seat, FALLBACK_CALLER_ORDER))

    # triple ron - abortive draw (all three opponents declared ron)
    settings = game_state.settings
    if settings.has_triple_ron_abort and len(ron_responses) == settings.triple_ron_count:
        result = process_abortive_draw(game_state, AbortiveDrawType.TRIPLE_RON)
        new_round_state = clear_pending_prompt(round_state)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = update_game_with_round(game_state, new_round_state)
        events: list[GameEvent] = [RoundEndEvent(result=result, target="all")]
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    # atamahane: cap to double_ron_count if double ron enabled, else single winner only
    max_winners = settings.double_ron_count if settings.has_double_ron else 1
    ron_seats = [r.seat for r in ron_responses[:max_winners]]
    is_chankan = prompt.call_type == CallType.CHANKAN
    ron_input = RonCallInput(
        ron_callers=ron_seats,
        tile_id=prompt.tile_id,
        discarder_seat=prompt.from_seat,
        is_chankan=is_chankan,
    )
    new_round_state, new_game_state, events = process_ron_call(
        round_state,
        game_state,
        ron_input,
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
    meld_input = MeldCallInput(
        caller_seat=best.seat,
        call_type=meld_type,
        tile_id=prompt.tile_id,
        sequence_tiles=best.sequence_tiles,
    )
    new_round_state, new_game_state, events = process_meld_call(
        round_state,
        game_state,
        meld_input,
    )
    new_round_state = clear_pending_prompt(new_round_state)
    new_game_state = update_game_with_round(new_game_state, new_round_state)

    if new_round_state.phase == RoundPhase.FINISHED:
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    if meld_type == MeldCallType.OPEN_KAN:
        # open kan draws from dead wall; include tile_id and available actions
        player = new_round_state.players[best.seat]
        events.append(create_draw_event(new_round_state, new_game_state, best.seat, tile_id=player.tiles[-1]))

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def _resolve_all_passed(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
) -> ActionResult:
    """
    Handle resolution when all callers passed on a RON or MELD prompt.

    Reveal deferred dora, advance turn, and draw for next player.
    Riichi finalization is handled separately by DISCARD prompt resolution.
    """
    events: list[GameEvent] = []

    new_round_state, dora_events = emit_deferred_dora_events(round_state)
    events.extend(dora_events)
    new_game_state = update_game_with_round(game_state, new_round_state)

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
    settings = game_state.settings
    old_dora_count = len(round_state.wall.dora_indicators)
    new_round_state, meld = call_added_kan(round_state, caller_seat, tile_id, settings)
    new_game_state = update_game_with_round(game_state, new_round_state)
    tile_ids = list(meld.tiles)

    events: list[GameEvent] = [
        MeldEvent(
            meld_type=MeldViewType.ADDED_KAN,
            caller_seat=caller_seat,
            tile_ids=tile_ids,
            called_tile_id=meld.called_tile,
            from_seat=meld.from_who,
        ),
    ]

    _maybe_emit_dora_event(old_dora_count, new_round_state, events)

    # check for four kans abortive draw
    if settings.has_suukaikan and check_four_kans(new_round_state, settings):
        result = process_abortive_draw(new_game_state, AbortiveDrawType.FOUR_KANS)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = update_game_with_round(new_game_state, new_round_state)
        events.append(RoundEndEvent(result=result, target="all"))
    # emit draw event for the dead wall tile with available actions
    elif new_round_state.phase == RoundPhase.PLAYING:
        player = new_round_state.players[caller_seat]
        drawn_tile = player.tiles[-1]
        events.append(create_draw_event(new_round_state, new_game_state, caller_seat, tile_id=drawn_tile))

    return new_round_state, new_game_state, events


def _finalize_discard_post_ron_check(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent], bool]:
    """Reveal deferred dora and finalize pending riichi after ron check passes.

    Called when no one called ron on a DISCARD prompt. The discard has "passed"
    the ron window, so deferred dora from prior open/added kan is revealed
    and pending riichi bets are deposited.

    Returns (new_round_state, new_game_state, events, riichi_finalized).
    """
    events: list[GameEvent] = []
    riichi_finalized = False

    new_round_state, dora_events = emit_deferred_dora_events(round_state)
    events.extend(dora_events)
    new_game_state = update_game_with_round(game_state, new_round_state)

    settings = game_state.settings
    discarder = new_round_state.players[prompt.from_seat]
    if discarder.discards and discarder.discards[-1].is_riichi_discard and not discarder.is_riichi:
        new_round_state, new_game_state = declare_riichi(
            new_round_state,
            new_game_state,
            prompt.from_seat,
            settings,
        )
        events.append(RiichiDeclaredEvent(seat=prompt.from_seat, target="all"))
        riichi_finalized = True

    return new_round_state, new_game_state, events, riichi_finalized


def _resolve_all_passed_discard(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    extra_events: list[GameEvent],
) -> ActionResult:
    """Handle all-passed for DISCARD prompts.

    Dora/riichi finalization is already done by the caller.
    Advance turn and draw for next player.
    """
    new_round_state = advance_turn(round_state)
    new_game_state = update_game_with_round(game_state, new_round_state)

    events = list(extra_events)
    if new_round_state.phase == RoundPhase.PLAYING:
        new_round_state, new_game_state, draw_events = process_draw_phase(new_round_state, new_game_state)
        events.extend(draw_events)

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def resolve_call_prompt(  # noqa: PLR0911
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

    if prompt.pending_seats:
        logger.error(
            "resolve_call_prompt called with pending seats",
            pending_count=len(prompt.pending_seats),
            pending_seats=prompt.pending_seats,
        )
        raise ValueError(f"cannot resolve call prompt: {len(prompt.pending_seats)} seats have not responded")

    ron_responses = [r for r in prompt.responses if r.action == GameAction.CALL_RON]
    meld_responses = [
        r for r in prompt.responses if r.action in (GameAction.CALL_PON, GameAction.CALL_CHI, GameAction.CALL_KAN)
    ]

    # priority 1: ron
    if ron_responses:
        logger.debug("call resolved: ron", winner_seats=[r.seat for r in ron_responses])
        return _resolve_ron_responses(round_state, game_state, prompt, ron_responses)

    # No ron -- finalize dora/riichi for DISCARD and MELD prompts.
    # Both prompt types originate from a discard, so the discarder may have a
    # pending riichi that needs to be finalized once no ron claim is made.
    extra_events: list[GameEvent] = []
    resolved_round = round_state
    resolved_game = game_state
    if prompt.call_type in (CallType.DISCARD, CallType.MELD):
        resolved_round, resolved_game, extra_events, riichi_finalized = _finalize_discard_post_ron_check(
            round_state,
            game_state,
            prompt,
        )

        # four riichi check only when this resolution finalized riichi
        settings = resolved_game.settings
        if riichi_finalized and settings.has_suucha_riichi and check_four_riichi(resolved_round, settings):
            result = process_abortive_draw(resolved_game, AbortiveDrawType.FOUR_RIICHI)
            new_round_state = clear_pending_prompt(resolved_round)
            new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
            new_game_state = update_game_with_round(resolved_game, new_round_state)
            extra_events.append(RoundEndEvent(result=result, target="all"))
            return ActionResult(extra_events, new_round_state=new_round_state, new_game_state=new_game_state)

    # priority 2: meld (pon/kan > chi, determined by caller priority in prompt)
    if meld_responses:
        best = pick_best_meld_response(meld_responses, prompt)
        if best is not None:
            logger.debug("call resolved: meld", caller_seat=best.seat, call_type=best.action.value)
            meld_result = _resolve_meld_response(resolved_round, resolved_game, prompt, best)
            # prepend dora/riichi events before meld events
            return ActionResult(
                extra_events + list(meld_result.events),
                new_round_state=meld_result.new_round_state,
                new_game_state=meld_result.new_game_state,
            )
        logger.error("all meld responses from unrecognized callers, treating as all-pass", count=len(meld_responses))

    # all passed
    logger.debug("call resolved: all passed")
    new_round_state = clear_pending_prompt(resolved_round)
    new_game_state = update_game_with_round(resolved_game, new_round_state)

    if prompt.call_type == CallType.CHANKAN:
        new_round_state, new_game_state, events = complete_added_kan_after_chankan_decline(
            new_round_state,
            new_game_state,
            prompt.from_seat,
            prompt.tile_id,
        )
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    # For DISCARD/MELD: dora/riichi already finalized above, just advance turn
    if prompt.call_type in (CallType.DISCARD, CallType.MELD):
        return _resolve_all_passed_discard(new_round_state, new_game_state, extra_events)

    return _resolve_all_passed(new_round_state, new_game_state)
