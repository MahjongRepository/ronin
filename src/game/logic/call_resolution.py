"""Call resolution subsystem -- resolve pending call prompts after all callers respond.

Handles ron resolution, meld resolution, all-passed flow, and chankan decline
completion. Extracted from action_handlers.py to give the call-resolution state
machine its own module and test surface.
"""

import logging

from game.logic.abortive import (
    AbortiveDrawType,
    check_four_kans,
    check_four_riichi,
    process_abortive_draw,
)
from game.logic.action_result import ActionResult, create_turn_event
from game.logic.enums import (
    MELD_CALL_PRIORITY,
    CallType,
    GameAction,
    KanType,
    MeldCallType,
    MeldViewType,
    RoundPhase,
)
from game.logic.events import (
    DrawEvent,
    GameEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
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
    advance_turn,
    clear_pending_prompt,
    update_game_with_round,
)
from game.logic.turn import (
    emit_deferred_dora_events,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
)
from game.logic.types import MeldCaller

logger = logging.getLogger(__name__)

# number of ron callers for triple ron abortive draw
TRIPLE_RON_COUNT = 3


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

    events.append(create_turn_event(new_round_state, new_game_state, best.seat))
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
            events.append(create_turn_event(new_round_state, new_game_state, caller_seat))

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
