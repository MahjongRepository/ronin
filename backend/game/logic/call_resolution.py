from typing import TYPE_CHECKING

import structlog

from game.logic.abortive import AbortiveDrawType
from game.logic.action_result import ActionResult
from game.logic.enums import (
    GameAction,
    KanType,
    MeldCallType,
    PromptKind,
    RoundPhase,
)
from game.logic.meld_wrapper import FrozenMeld
from game.logic.settings import TRIPLE_RON_COUNT
from game.logic.state_utils import (
    clear_pending_prompt,
    update_game_with_round,
)
from game.logic.tiles import tile_to_34
from game.logic.turn import (
    _abort_round,
    draw_for_next_player,
    execute_unrobbed_kan,
    pass_ron_window,
    process_meld_call,
    process_ron_call,
)
from game.logic.types import MeldCallInput, RobbedKan, RonCallInput

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


def pick_best_meld_response(meld_responses: list[CallResponse]) -> CallResponse:
    """
    Pick the highest-priority meld response.

    Priority comes from the call actually made, not the best one the seat was offered: a pon or kan beats a chi. No
    seat order is needed: one seat at most can pon or kan a discard, and only the next seat can chi it.
    """
    return min(meld_responses, key=lambda r: r.action == GameAction.CALL_CHI)


def _kan_open_to_chankan(round_state: MahjongRoundState, prompt: PendingCallPrompt) -> RobbedKan:
    """
    Return the kan a chankan prompt offers to rob: an added kan when its declarer holds a pon of the tile, else the
    closed kan kokushi musou may rob.
    """
    player = round_state.players[prompt.from_seat]
    tile_34 = tile_to_34(prompt.tile_id)
    has_pon = any(m.meld_type == FrozenMeld.PON and tile_to_34(m.tiles[0]) == tile_34 for m in player.melds)
    return RobbedKan(
        seat=prompt.from_seat,
        tile_id=prompt.tile_id,
        kan_type=KanType.ADDED if has_pon else KanType.CLOSED,
    )


def _resolve_ron_responses(
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

    robbed_kan = _kan_open_to_chankan(game_state.round_state, prompt) if prompt.kind == PromptKind.CHANKAN else None

    # triple ron - abortive draw (all three opponents declared ron)
    settings = game_state.settings
    if settings.has_triple_ron_abort and len(ron_responses) == TRIPLE_RON_COUNT:
        new_game_state, events = _abort_round(
            game_state,
            draw_type=AbortiveDrawType.TRIPLE_RON,
            events=[],
            ron_seats=[r.seat for r in ron_responses],
            robbed_kan=robbed_kan,
        )
        return ActionResult(events, state=new_game_state)

    # atamahane: cap to double_ron_count if double ron enabled, else single winner only
    max_winners = settings.double_ron_count if settings.has_double_ron else 1
    ron_seats = [r.seat for r in ron_responses[:max_winners]]
    head_bumped_seats = [r.seat for r in ron_responses[max_winners:]]
    ron_input = RonCallInput(
        ron_callers=ron_seats,
        tile_id=prompt.tile_id,
        discarder_seat=prompt.from_seat,
        robbed_kan=robbed_kan,
        head_bumped_seats=head_bumped_seats or None,
    )
    new_game_state, events = process_ron_call(game_state, ron_input=ron_input)
    return ActionResult(events, state=new_game_state)


def resolve_call_prompt(game_state: MahjongGameState) -> ActionResult:
    """
    Resolve the round's pending call prompt once every caller has responded.

    Clear the prompt, then execute the winning response by priority (ron > pon/kan > chi > all pass). A discard nobody
    ronned passes the ron window (pass_ron_window) before a meld on it executes; a kan nobody robbed completes with its
    rinshan draw.
    """
    prompt = game_state.round_state.pending_call_prompt
    if prompt is None:
        raise AssertionError("resolve_call_prompt called with no pending call prompt")

    game_state = update_game_with_round(game_state, clear_pending_prompt(game_state.round_state))
    ron_responses = [r for r in prompt.responses if r.action == GameAction.CALL_RON]
    meld_responses = [
        r for r in prompt.responses if r.action in (GameAction.CALL_PON, GameAction.CALL_CHI, GameAction.CALL_KAN)
    ]

    # priority 1: ron
    if ron_responses:
        logger.debug("call resolved: ron declared", ron_seats=[r.seat for r in ron_responses])
        return _resolve_ron_responses(game_state, prompt=prompt, ron_responses=ron_responses)

    if prompt.kind == PromptKind.CHANKAN:
        logger.debug("call resolved: all passed")
        new_game_state, events = execute_unrobbed_kan(game_state, _kan_open_to_chankan(game_state.round_state, prompt))
        return ActionResult(events, state=new_game_state)

    new_game_state, events = pass_ron_window(game_state, discarder_seat=prompt.from_seat)
    if new_game_state.round_state.phase == RoundPhase.FINISHED:
        return ActionResult(events, state=new_game_state)

    if meld_responses:
        best = pick_best_meld_response(meld_responses)
        logger.debug("call resolved: meld", caller_seat=best.seat, call_type=best.action.value)
        meld_input = MeldCallInput(
            caller_seat=best.seat,
            call_type=_ACTION_TO_MELD_CALL_TYPE[best.action],
            tile_id=prompt.tile_id,
            sequence_tiles=best.sequence_tiles,
        )
        new_game_state, meld_events = process_meld_call(new_game_state, meld_input=meld_input)
        return ActionResult(events + meld_events, state=new_game_state)

    logger.debug("call resolved: all passed")
    new_game_state, draw_events = draw_for_next_player(new_game_state)
    return ActionResult(events + draw_events, state=new_game_state)
