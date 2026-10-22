from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.logic.enums import GameAction, GamePhase
from game.logic.events import EventType
from game.logic.mahjong_service import MahjongGameService
from game.replay.loader import ReplayLoadError
from game.replay.models import (
    ReplayError,
    ReplayInput,
    ReplayInputAfterGameEndError,
    ReplayInputEvent,
    ReplayInvariantError,
    ReplayStep,
    ReplayStepLimitError,
    ReplayTrace,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from game.logic.service import GameService
    from game.logic.state import MahjongGameState


_CALL_RESPONSE_ACTIONS = frozenset(
    {
        GameAction.CALL_PON,
        GameAction.CALL_CHI,
        GameAction.CALL_KAN,
        GameAction.CALL_RON,
    },
)


@dataclass(frozen=True)
class ReplayOptions:
    """
    Configuration for a replay run.
    """

    game_id: str = ""
    strict: bool = True
    auto_confirm_rounds: bool = True
    auto_pass_calls: bool = True
    max_steps: int = 10_000


@dataclass(frozen=True)
class _ReplayRunContext:
    """
    Bundle service + options for internal replay functions.
    """

    service: GameService
    opts: ReplayOptions


@dataclass(frozen=True)
class _ReplaySeating:
    """
    Map the replay's player names to the seats the game gave them, both ways.
    """

    seat_by_player: dict[str, int]
    player_by_seat: dict[int, str]


def _default_service_factory() -> GameService:
    return MahjongGameService(auto_cleanup=False)


def run_replay(
    replay: ReplayInput,
    opts: ReplayOptions | None = None,
    *,
    service_factory: Callable[[], GameService] | None = None,
) -> ReplayTrace:
    """
    Run a deterministic replay through the game service.

    Feed replay input events through the service and capture a full trace with state_before/state_after for each
    transition.
    """
    resolved_opts = opts or ReplayOptions()
    if not resolved_opts.game_id:
        resolved_opts = ReplayOptions(
            game_id=f"replay-{uuid.uuid4().hex}",
            strict=resolved_opts.strict,
            auto_confirm_rounds=resolved_opts.auto_confirm_rounds,
            auto_pass_calls=resolved_opts.auto_pass_calls,
            max_steps=resolved_opts.max_steps,
        )

    factory = service_factory or _default_service_factory
    service = factory()
    ctx = _ReplayRunContext(service=service, opts=resolved_opts)

    try:
        return _execute_replay(ctx, replay)
    finally:
        service.cleanup_game(resolved_opts.game_id)


def _execute_replay(
    ctx: _ReplayRunContext,
    replay: ReplayInput,
) -> ReplayTrace:
    """
    Core replay execution loop.
    """
    opts = ctx.opts
    service = ctx.service

    if opts.auto_confirm_rounds:
        _reject_manual_confirm_rounds(replay)

    if opts.auto_pass_calls:
        _reject_manual_pass(replay)

    start = service.start_game(
        opts.game_id,
        list(replay.player_names),
        seed=replay.seed,
        wall=list(replay.wall) if replay.wall is not None else None,
    )

    initial_state = _require_state(
        service, game_id=opts.game_id, message="start_game completed but game state is missing"
    )
    seat_by_player = dict(zip(replay.player_names, start.seats, strict=True))
    seating = _ReplaySeating(
        seat_by_player=seat_by_player,
        player_by_seat={seat: name for name, seat in seat_by_player.items()},
    )

    steps: list[ReplayStep] = []
    step_count = 0
    for input_event in replay.events:
        _check_step_limit(step_count, opts.max_steps)
        current_state = _require_state(
            service, game_id=opts.game_id, message="game state disappeared during replay execution"
        )
        if current_state.game_phase == GamePhase.FINISHED:
            if opts.strict:
                raise ReplayInputAfterGameEndError(
                    f"Input remains after game end at step {step_count}: {input_event}",
                )

            break

        step_count = _maybe_confirm_round(ctx, seating=seating, steps=steps, step_count=step_count)

        if opts.auto_pass_calls:
            step_count = _handle_auto_pass_for_input(
                ctx, input_event=input_event, seating=seating, steps=steps, step_count=step_count
            )

        # Auto-pass resolution may end the round (e.g. exhaustive draw after
        # the last call prompt resolves). Re-check for round advance.
        step_count = _maybe_confirm_round(ctx, seating=seating, steps=steps, step_count=step_count)

        # Re-check game phase: auto-pass or round confirmation may have ended the game
        post_synthetic_state = _require_state(
            service,
            game_id=opts.game_id,
            message="game state disappeared after synthetic steps",
        )
        if post_synthetic_state.game_phase == GamePhase.FINISHED:
            if opts.strict:
                raise ReplayInputAfterGameEndError(
                    f"Input remains after game end at step {step_count}: {input_event}",
                )

            break

        step_count = _process_input_event(
            ctx,
            input_event=input_event,
            seat=seat_by_player[input_event.player_name],
            steps=steps,
            step_count=step_count,
        )

    # Handle any trailing call prompt after all input events are consumed
    if opts.auto_pass_calls:
        step_count = _inject_pass_calls(ctx, seating=seating, steps=steps, step_count=step_count)

    # Handle any trailing round advance after all input events are consumed
    step_count = _maybe_confirm_round(ctx, seating=seating, steps=steps, step_count=step_count)

    final_state = _require_state(service, game_id=opts.game_id, message="replay finished but final state is missing")
    return ReplayTrace(
        seed=replay.seed,
        rng_version=replay.rng_version,
        seat_by_player=seat_by_player,
        startup_events=tuple(start.events),
        initial_state=initial_state,
        steps=tuple(steps),
        final_state=final_state,
    )


def _reject_manual_confirm_rounds(replay: ReplayInput) -> None:
    """
    Reject CONFIRM_ROUND events in input when auto_confirm_rounds is enabled.

    When auto_confirm_rounds=True, the runner injects synthetic CONFIRM_ROUND steps automatically. Manual CONFIRM_ROUND
    events in the input would conflict and produce duplicate confirmation errors.
    """
    confirm_indices = [i for i, event in enumerate(replay.events) if event.action == GameAction.CONFIRM_ROUND]
    if confirm_indices:
        raise ReplayLoadError(
            f"ReplayInput.events contains CONFIRM_ROUND at indices {confirm_indices}, "
            "but auto_confirm_rounds=True. Either remove CONFIRM_ROUND events from "
            "the input or set auto_confirm_rounds=False.",
        )


def _reject_manual_pass(replay: ReplayInput) -> None:
    """
    Reject PASS events in input when auto_pass_calls is enabled.

    When auto_pass_calls=True, the runner injects synthetic PASS steps automatically. Manual PASS events in the input
    would conflict and produce duplicate pass errors.
    """
    pass_indices = [i for i, event in enumerate(replay.events) if event.action == GameAction.PASS]
    if pass_indices:
        raise ReplayLoadError(
            f"ReplayInput.events contains PASS at indices {pass_indices}, "
            "but auto_pass_calls=True. Either remove PASS events from "
            "the input or set auto_pass_calls=False.",
        )


def _check_step_limit(step_count: int, max_steps: int) -> None:
    if step_count >= max_steps:
        raise ReplayStepLimitError(f"Replay exceeded {max_steps} steps")


def _require_state(
    service: GameService,
    *,
    game_id: str,
    message: str,
) -> MahjongGameState:
    state = service.get_game_state(game_id)
    if state is None:
        raise ReplayInvariantError(message)

    return state


def _process_input_event(
    ctx: _ReplayRunContext,
    input_event: ReplayInputEvent,
    seat: int,
    steps: list[ReplayStep],
    step_count: int,
) -> int:
    """
    Process one player input event and append to steps.

    A rule judgment comes back as the ErrorEvent the live server sends; structural input (InvalidGameActionError) or a
    server fault raises and fails the replay.
    """
    state_before = _require_state(
        ctx.service, game_id=ctx.opts.game_id, message="game state disappeared before replay action"
    )

    events = ctx.service.handle_action(
        game_id=ctx.opts.game_id,
        seat=seat,
        action=input_event.action,
        data=dict(input_event.data),
    ).events

    if ctx.opts.strict:
        errors = [e for e in events if e.event == EventType.ERROR]
        if errors:
            raise ReplayError(step_index=step_count, event=input_event, errors=errors)

    state_after = _require_state(
        ctx.service, game_id=ctx.opts.game_id, message="game state disappeared after replay action"
    )
    steps.append(
        ReplayStep(
            input_event=input_event,
            emitted_events=tuple(events),
            state_before=state_before,
            state_after=state_after,
        ),
    )
    return step_count + 1


def _maybe_confirm_round(
    ctx: _ReplayRunContext,
    seating: _ReplaySeating,
    steps: list[ReplayStep],
    step_count: int,
) -> int:
    """
    Inject round confirmations if a round advance is pending.
    """
    if ctx.opts.auto_confirm_rounds and ctx.service.is_round_advance_pending(ctx.opts.game_id):
        step_count = _inject_round_confirmations(ctx, seating=seating, steps=steps, step_count=step_count)
        _check_step_limit(step_count, ctx.opts.max_steps)

    return step_count


def _inject_round_confirmations(
    ctx: _ReplayRunContext,
    seating: _ReplaySeating,
    steps: list[ReplayStep],
    step_count: int,
) -> int:
    """
    Inject synthetic CONFIRM_ROUND steps for all pending players.
    """
    game_id = ctx.opts.game_id
    for seat in ctx.service.get_pending_round_advance_seats(game_id):
        _check_step_limit(step_count, ctx.opts.max_steps)
        player_name = seating.player_by_seat[seat]

        synthetic_before = _require_state(
            ctx.service,
            game_id=game_id,
            message="game state disappeared before synthetic confirm_round",
        )

        confirm_events = ctx.service.handle_action(
            game_id=game_id, seat=seat, action=GameAction.CONFIRM_ROUND, data={}
        ).events

        if ctx.opts.strict:
            errors = [e for e in confirm_events if e.event == EventType.ERROR]
            if errors:
                synthetic_event = ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.CONFIRM_ROUND,
                )
                raise ReplayError(step_index=step_count, event=synthetic_event, errors=errors)

        state_after = _require_state(
            ctx.service,
            game_id=game_id,
            message="game state disappeared after synthetic confirm_round",
        )
        steps.append(
            ReplayStep(
                input_event=ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.CONFIRM_ROUND,
                ),
                synthetic=True,
                emitted_events=tuple(confirm_events),
                state_before=synthetic_before,
                state_after=state_after,
            ),
        )
        step_count += 1

    return step_count


def _handle_auto_pass_for_input(
    ctx: _ReplayRunContext,
    input_event: ReplayInputEvent,
    seating: _ReplaySeating,
    steps: list[ReplayStep],
    step_count: int,
) -> int:
    """
    Handle auto-pass logic before processing an input event.

    If a call prompt is pending:
    - If the input is a call response from a pending seat, skip that seat
      (it will be processed normally) and auto-pass the remaining seats.
    - Otherwise, auto-pass all pending seats first.
    """
    state = _require_state(
        ctx.service, game_id=ctx.opts.game_id, message="game state disappeared before auto-pass check"
    )
    prompt = state.round_state.pending_call_prompt
    if prompt is None:
        return step_count

    input_seat = seating.seat_by_player[input_event.player_name]
    is_call_response = input_event.action in _CALL_RESPONSE_ACTIONS and input_seat in prompt.pending_seats
    exclude_seats = frozenset({input_seat}) if is_call_response else frozenset()
    return _inject_pass_calls(ctx, seating=seating, steps=steps, step_count=step_count, exclude_seats=exclude_seats)


def _inject_pass_calls(
    ctx: _ReplayRunContext,
    *,
    seating: _ReplaySeating,
    steps: list[ReplayStep],
    step_count: int,
    exclude_seats: frozenset[int] = frozenset(),
) -> int:
    """
    Inject synthetic PASS steps for pending call prompt seats.

    exclude_seats: seats to skip (e.g., the seat of the next input event
    that is itself a call response).
    """
    game_id = ctx.opts.game_id
    state = _require_state(ctx.service, game_id=game_id, message="game state disappeared before auto-pass injection")
    prompt = state.round_state.pending_call_prompt
    if prompt is None:
        return step_count

    seats_to_pass = sorted(prompt.pending_seats - exclude_seats)
    for seat in seats_to_pass:
        # Re-read prompt state: earlier PASS may have resolved the prompt entirely
        fresh_state = _require_state(
            ctx.service, game_id=game_id, message="game state disappeared during auto-pass injection"
        )
        if fresh_state.round_state.pending_call_prompt is None:
            break

        _check_step_limit(step_count, ctx.opts.max_steps)
        player_name = seating.player_by_seat[seat]

        synthetic_before = _require_state(
            ctx.service, game_id=game_id, message="game state disappeared before synthetic pass"
        )

        pass_events = ctx.service.handle_action(game_id=game_id, seat=seat, action=GameAction.PASS, data={}).events

        if ctx.opts.strict:
            errors = [e for e in pass_events if e.event == EventType.ERROR]
            if errors:
                synthetic_event = ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.PASS,
                )
                raise ReplayError(step_index=step_count, event=synthetic_event, errors=errors)

        state_after = _require_state(
            ctx.service, game_id=game_id, message="game state disappeared after synthetic pass"
        )
        steps.append(
            ReplayStep(
                input_event=ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.PASS,
                ),
                synthetic=True,
                emitted_events=tuple(pass_events),
                state_before=synthetic_before,
                state_after=state_after,
            ),
        )
        step_count += 1

    return step_count
