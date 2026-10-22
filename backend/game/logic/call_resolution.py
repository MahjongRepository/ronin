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
    MELD_CALL_PRIORITY,
    GameAction,
    MeldCallType,
    MeldViewType,
    PromptKind,
    RoundPhase,
)
from game.logic.events import (
    GameEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
)
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import call_added_kan, call_closed_kan
from game.logic.riichi import declare_riichi
from game.logic.settings import NUM_PLAYERS
from game.logic.state_utils import (
    advance_turn,
    clear_pending_prompt,
    update_game_with_round,
)
from game.logic.tiles import tile_to_34
from game.logic.turn import (
    _maybe_emit_dora_event,
    emit_deferred_dora_events,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
)
from game.logic.types import MeldCallInput, RonCallInput

if TYPE_CHECKING:
    from game.logic.state import (
        CallResponse,
        MahjongGameState,
        MahjongRoundState,
        PendingCallPrompt,
    )

logger = structlog.get_logger()

_ACTION_TO_MELD_CALL_TYPE = {
    GameAction.CALL_PON: MeldCallType.PON,
    GameAction.CALL_CHI: MeldCallType.CHI,
    GameAction.CALL_KAN: MeldCallType.OPEN_KAN,
}


def pick_best_meld_response(
    meld_responses: list[CallResponse],
    prompt: PendingCallPrompt,
) -> CallResponse:
    """
    Pick the highest-priority meld response.

    Priority comes from the call actually made, not the best one the seat was offered: kan > pon > chi. Tie-break:
    counter-clockwise distance from the discarder (closer = higher priority). Every response is a call the prompt
    offered its seat (validated on submit).
    """

    def sort_key(response: CallResponse) -> tuple[int, int]:
        priority = MELD_CALL_PRIORITY[_ACTION_TO_MELD_CALL_TYPE[response.action]]
        distance = (response.seat - prompt.from_seat) % NUM_PLAYERS
        return priority, distance

    return min(meld_responses, key=sort_key)


def _resolve_ron_responses(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
    ron_responses: list[CallResponse],
) -> ActionResult:
    """
    Resolve ron responses from the pending call prompt.
    """
    # sort by position in prompt.callers (counter-clockwise from discarder)
    caller_order = {c.seat: i for i, c in enumerate(prompt.callers)}
    ron_responses = sorted(ron_responses, key=lambda r: caller_order[r.seat])

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
    is_chankan = prompt.kind == PromptKind.CHANKAN
    ron_input = RonCallInput(
        ron_callers=ron_seats,
        tile_id=prompt.tile_id,
        discarder_seat=prompt.from_seat,
        is_chankan=is_chankan,
    )
    new_round_state, new_game_state, events = process_ron_call(
        round_state,
        game_state,
        ron_input=ron_input,
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
    """
    Resolve the winning meld response from the pending call prompt.
    """
    meld_type = _ACTION_TO_MELD_CALL_TYPE[best.action]
    meld_input = MeldCallInput(
        caller_seat=best.seat,
        call_type=meld_type,
        tile_id=prompt.tile_id,
        sequence_tiles=best.sequence_tiles,
    )
    new_round_state, new_game_state, events = process_meld_call(
        round_state,
        game_state,
        meld_input=meld_input,
    )

    new_round_state = clear_pending_prompt(new_round_state)
    new_game_state = update_game_with_round(new_game_state, new_round_state)

    if new_round_state.phase == RoundPhase.FINISHED:
        return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)

    if meld_type == MeldCallType.OPEN_KAN:
        # open kan draws from dead wall; include tile_id and available actions
        player = new_round_state.players[best.seat]
        events.append(create_draw_event(new_round_state, new_game_state, seat=best.seat, tile_id=player.tiles[-1]))

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def _complete_kan_after_chankan_decline(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
    *,
    is_closed: bool,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Shared logic for completing a kan after chankan opportunity was declined.

    Executes the kan call, emits meld/dora events, checks four kans abort, and emits the dead wall draw event.
    """
    settings = game_state.settings
    old_dora_count = len(round_state.wall.dora_indicators)

    if is_closed:
        new_round_state, meld = call_closed_kan(round_state, seat=caller_seat, tile_id=tile_id, settings=settings)
        meld_event = MeldEvent(
            meld_type=MeldViewType.CLOSED_KAN,
            caller_seat=caller_seat,
            tile_ids=list(meld.tiles),
        )
    else:
        new_round_state, meld = call_added_kan(round_state, seat=caller_seat, tile_id=tile_id, settings=settings)
        meld_event = MeldEvent(
            meld_type=MeldViewType.ADDED_KAN,
            caller_seat=caller_seat,
            tile_ids=list(meld.tiles),
            called_tile_id=meld.called_tile,
            from_seat=meld.from_who,
        )

    new_game_state = update_game_with_round(game_state, new_round_state)
    events: list[GameEvent] = [meld_event]

    _maybe_emit_dora_event(old_dora_count=old_dora_count, new_round_state=new_round_state, events=events)

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
        events.append(create_draw_event(new_round_state, new_game_state, seat=caller_seat, tile_id=drawn_tile))

    return new_round_state, new_game_state, events


def complete_added_kan_after_chankan_decline(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Complete an added kan after chankan opportunity was declined.

    Called when all players pass on a chankan opportunity. Furiten is applied per-caller in handle_pass before
    resolution.
    """
    return _complete_kan_after_chankan_decline(
        round_state,
        game_state,
        caller_seat,
        tile_id,
        is_closed=False,
    )


def complete_closed_kan_after_chankan_decline(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    caller_seat: int,
    tile_id: int,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent]]:
    """
    Complete a closed kan after kokushi chankan opportunity was declined.

    Called when all players pass on a kokushi chankan opportunity for ankan.
    """
    return _complete_kan_after_chankan_decline(
        round_state,
        game_state,
        caller_seat,
        tile_id,
        is_closed=True,
    )


def _finalize_discard_post_ron_check(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
) -> tuple[MahjongRoundState, MahjongGameState, list[GameEvent], bool]:
    """
    Reveal deferred dora and finalize pending riichi after ron check passes.

    Called when no one called ron on a DISCARD prompt. The discard has "passed" the ron window, so deferred dora from
    prior open/added kan is revealed and pending riichi bets are deposited.

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
            seat=prompt.from_seat,
            settings=settings,
        )
        events.append(RiichiDeclaredEvent(seat=prompt.from_seat, target="all"))
        riichi_finalized = True

    return new_round_state, new_game_state, events, riichi_finalized


def _resolve_all_passed_discard(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    extra_events: list[GameEvent],
) -> ActionResult:
    """
    Handle all-passed for DISCARD prompts.

    Dora/riichi finalization is already done by the caller. Advance turn and draw for next player.
    """
    new_round_state = advance_turn(round_state)
    new_game_state = update_game_with_round(game_state, new_round_state)

    events = list(extra_events)
    if new_round_state.phase == RoundPhase.PLAYING:
        new_round_state, new_game_state, draw_events = process_draw_phase(new_round_state, new_game_state)
        events.extend(draw_events)

    return ActionResult(events, new_round_state=new_round_state, new_game_state=new_game_state)


def _resolve_chankan_decline(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
    prompt: PendingCallPrompt,
) -> ActionResult:
    """
    Complete the kan after all chankan rob attempts were declined.
    """
    player = round_state.players[prompt.from_seat]
    t34 = tile_to_34(prompt.tile_id)
    has_pon = any(m.meld_type == FrozenMeld.PON and tile_to_34(m.tiles[0]) == t34 for m in player.melds)
    if has_pon:
        new_rs, new_gs, events = complete_added_kan_after_chankan_decline(
            round_state,
            game_state,
            caller_seat=prompt.from_seat,
            tile_id=prompt.tile_id,
        )
    else:
        new_rs, new_gs, events = complete_closed_kan_after_chankan_decline(
            round_state,
            game_state,
            caller_seat=prompt.from_seat,
            tile_id=prompt.tile_id,
        )

    return ActionResult(events, new_round_state=new_rs, new_game_state=new_gs)


def resolve_call_prompt(
    round_state: MahjongRoundState,
    game_state: MahjongGameState,
) -> ActionResult:
    """
    Resolve the round's pending call prompt once every caller has responded.

    Pick the winning response by priority (ron > pon/kan > chi > all pass) and execute it. Clear the pending prompt.
    Returns ActionResult with events and new state.
    """
    prompt = round_state.pending_call_prompt
    if prompt is None:
        raise AssertionError("resolve_call_prompt called with no pending call prompt")

    ron_responses = [r for r in prompt.responses if r.action == GameAction.CALL_RON]
    meld_responses = [
        r for r in prompt.responses if r.action in (GameAction.CALL_PON, GameAction.CALL_CHI, GameAction.CALL_KAN)
    ]

    # priority 1: ron
    if ron_responses:
        logger.debug("call resolved: ron", winner_seats=[r.seat for r in ron_responses])
        return _resolve_ron_responses(round_state, game_state, prompt=prompt, ron_responses=ron_responses)

    if prompt.kind == PromptKind.CHANKAN:
        logger.debug("call resolved: all passed")
        new_round_state = clear_pending_prompt(round_state)
        new_game_state = update_game_with_round(game_state, new_round_state)
        return _resolve_chankan_decline(new_round_state, new_game_state, prompt=prompt)

    resolved_round, resolved_game, extra_events, riichi_finalized = _finalize_discard_post_ron_check(
        round_state,
        game_state,
        prompt=prompt,
    )

    settings = resolved_game.settings
    if riichi_finalized and settings.has_suucha_riichi and check_four_riichi(resolved_round):
        result = process_abortive_draw(resolved_game, AbortiveDrawType.FOUR_RIICHI)
        new_round_state = clear_pending_prompt(resolved_round)
        new_round_state = new_round_state.model_copy(update={"phase": RoundPhase.FINISHED})
        new_game_state = update_game_with_round(resolved_game, new_round_state)

        extra_events.append(RoundEndEvent(result=result, target="all"))
        return ActionResult(extra_events, new_round_state=new_round_state, new_game_state=new_game_state)

    if meld_responses:
        best = pick_best_meld_response(meld_responses, prompt)
        logger.debug("call resolved: meld", caller_seat=best.seat, call_type=best.action.value)
        meld_result = _resolve_meld_response(resolved_round, resolved_game, prompt=prompt, best=best)
        return ActionResult(
            extra_events + list(meld_result.events),
            new_round_state=meld_result.new_round_state,
            new_game_state=meld_result.new_game_state,
        )

    logger.debug("call resolved: all passed")
    new_round_state = clear_pending_prompt(resolved_round)
    new_game_state = update_game_with_round(resolved_game, new_round_state)
    return _resolve_all_passed_discard(new_round_state, new_game_state, extra_events=extra_events)
