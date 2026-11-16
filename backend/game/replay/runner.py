from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from game.engine import Chi, EventType, GamePhase, Kan, KanType, MahjongGameService, Pass, Pon, Ron, WaitKind
from game.replay.loader import ReplayLoadError
from game.replay.models import (
    ReplayError,
    ReplayInput,
    ReplayInputAfterGameEndError,
    ReplayInputEvent,
    ReplayStep,
    ReplayStepLimitError,
    ReplayTrace,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from game.engine import GameRuntime, GameService


@dataclass(frozen=True)
class ReplayOptions:
    """
    Configuration for a replay run.
    """

    game_id: str = ""
    strict: bool = True
    advance_rounds: bool = True
    auto_pass_calls: bool = True
    max_steps: int = 10_000


@dataclass(frozen=True)
class _ReplayRunContext:
    """
    Bundle the service, the options, the replayed input events and the replayed game's runtime for internal replay
    functions.
    """

    service: GameService
    opts: ReplayOptions
    events: tuple[ReplayInputEvent, ...]
    runtime: GameRuntime


@dataclass(frozen=True)
class _ReplaySeating:
    """
    Map the replay's player names to the seats the game gave them, both ways.
    """

    seat_by_player: dict[str, int]
    player_by_seat: dict[int, str]


def _default_service_factory() -> GameService:
    return MahjongGameService()


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
        resolved_opts = replace(resolved_opts, game_id=f"replay-{uuid.uuid4().hex}")

    factory = service_factory or _default_service_factory
    return _execute_replay(factory(), resolved_opts, replay)


def _execute_replay(
    service: GameService,
    opts: ReplayOptions,
    replay: ReplayInput,
) -> ReplayTrace:
    """
    Core replay execution loop.
    """
    if opts.auto_pass_calls:
        _reject_manual_pass(replay)

    start = service.start_game(
        opts.game_id,
        list(replay.player_names),
        seed=replay.seed,
        walls=replay.walls,
        start=replay.start,
    )
    runtime = start.runtime
    begun = service.begin_round(runtime)
    ctx = _ReplayRunContext(service=service, opts=opts, events=replay.events, runtime=runtime)

    initial_state = runtime.state
    seat_by_player = dict(zip(replay.player_names, start.seats, strict=True))
    seating = _ReplaySeating(
        seat_by_player=seat_by_player,
        player_by_seat={seat: name for name, seat in seat_by_player.items()},
    )

    steps: list[ReplayStep] = []
    for index, input_event in enumerate(replay.events):
        _check_step_limit(len(steps), opts.max_steps)
        if runtime.state.game_phase == GamePhase.FINISHED:
            if opts.strict:
                raise ReplayInputAfterGameEndError(
                    f"Input remains after game end at step {len(steps)}: {input_event}",
                )

            break

        _maybe_advance_round(ctx, steps=steps)

        if opts.auto_pass_calls:
            _handle_auto_pass_for_input(ctx, index=index, seating=seating, steps=steps)

        # Auto-pass resolution may end the round (e.g. exhaustive draw after
        # the last call prompt resolves). Re-check for round advance.
        _maybe_advance_round(ctx, steps=steps)

        if runtime.state.game_phase == GamePhase.FINISHED:
            if opts.strict:
                raise ReplayInputAfterGameEndError(
                    f"Input remains after game end at step {len(steps)}: {input_event}",
                )

            break

        _run_step(ctx, steps=steps, seat=seat_by_player[input_event.player_name], input_event=input_event)

    # Handle any trailing call prompt after all input events are consumed
    if opts.auto_pass_calls:
        _inject_pass_calls(ctx, seating=seating, steps=steps)

    # Handle any trailing round advance after all input events are consumed
    _maybe_advance_round(ctx, steps=steps)

    return ReplayTrace(
        seed=replay.seed,
        rng_version=replay.rng_version,
        seat_by_player=seat_by_player,
        startup_events=(*start.events, *begun.events),
        initial_state=initial_state,
        steps=tuple(steps),
        final_state=runtime.state,
    )


def _reject_manual_pass(replay: ReplayInput) -> None:
    """
    Reject PASS events in input when auto_pass_calls is enabled.

    When auto_pass_calls=True, the runner injects synthetic PASS steps automatically. Manual PASS events in the input
    would conflict and produce duplicate pass errors.
    """
    pass_indices = [i for i, event in enumerate(replay.events) if isinstance(event.action, Pass)]
    if pass_indices:
        raise ReplayLoadError(
            f"ReplayInput.events contains PASS at indices {pass_indices}, "
            "but auto_pass_calls=True. Either remove PASS events from "
            "the input or set auto_pass_calls=False.",
        )


def _check_step_limit(step_count: int, max_steps: int) -> None:
    if step_count >= max_steps:
        raise ReplayStepLimitError(f"Replay exceeded {max_steps} steps")


def _run_step(
    ctx: _ReplayRunContext,
    *,
    steps: list[ReplayStep],
    seat: int,
    input_event: ReplayInputEvent,
    synthetic: bool = False,
) -> None:
    """
    Run one input or synthetic action through the service and append its step.

    The step limit is checked first. In strict mode a rule judgment (the ErrorEvent the live server sends) fails the
    replay at this step; structural input (InvalidGameActionError) or a server fault raises in either mode.
    """
    _check_step_limit(len(steps), ctx.opts.max_steps)

    state_before = ctx.runtime.state
    events = ctx.service.act(ctx.runtime, seat, input_event.action).events

    if ctx.opts.strict:
        errors = [e for e in events if e.type == EventType.ERROR]
        if errors:
            raise ReplayError(step_index=len(steps), event=input_event, errors=errors)

    steps.append(
        ReplayStep(
            input_event=input_event,
            synthetic=synthetic,
            emitted_events=tuple(events),
            state_before=state_before,
            state_after=ctx.runtime.state,
        ),
    )


def _maybe_advance_round(ctx: _ReplayRunContext, *, steps: list[ReplayStep]) -> None:
    """
    Deal the next round and let its dealer draw, as one synthetic step with no input, when the game waits on a round's
    end.
    """
    if not ctx.opts.advance_rounds or ctx.service.get_awaiting(ctx.runtime).kind != WaitKind.ROUND_OVER:
        return

    _check_step_limit(len(steps), ctx.opts.max_steps)
    state_before = ctx.runtime.state
    dealt = ctx.service.deal_next_round(ctx.runtime)
    begun = ctx.service.begin_round(ctx.runtime)
    steps.append(
        ReplayStep(
            input_event=None,
            synthetic=True,
            emitted_events=(*dealt.events, *begun.events),
            state_before=state_before,
            state_after=ctx.runtime.state,
        ),
    )
    _check_step_limit(len(steps), ctx.opts.max_steps)


def _handle_auto_pass_for_input(
    ctx: _ReplayRunContext,
    *,
    index: int,
    seating: _ReplaySeating,
    steps: list[ReplayStep],
) -> None:
    """
    Handle auto-pass logic before processing the input event at index.

    If a call prompt is pending:
    - If the input is a call response from a pending seat, skip that seat
      (it will be processed normally) and auto-pass the remaining seats.
      A ron also spares the seats of the rons that directly follow it in the
      input: a double or triple ron is recorded as consecutive Ron inputs
      answering the same prompt.
    - Otherwise, auto-pass all pending seats first.
    """
    prompt = ctx.runtime.state.round_state.pending_call_prompt
    if prompt is None:
        return

    events = ctx.events
    input_event = events[index]
    input_seat = seating.seat_by_player[input_event.player_name]
    if input_seat not in prompt.pending_seats or not _is_call_response(input_event):
        _inject_pass_calls(ctx, seating=seating, steps=steps)
        return

    responding_seats = {input_seat}
    if isinstance(input_event.action, Ron):
        for later_index in range(index + 1, len(events)):
            later_event = events[later_index]
            if not isinstance(later_event.action, Ron):
                break

            responding_seats.add(seating.seat_by_player[later_event.player_name])

    _inject_pass_calls(ctx, seating=seating, steps=steps, exclude_seats=frozenset(responding_seats))


def _is_call_response(input_event: ReplayInputEvent) -> bool:
    """
    Tell whether the input answers a call prompt: a closed or added kan is a turn action that needs a new own turn.
    """
    action = input_event.action
    if isinstance(action, Kan):
        return action.kan_type == KanType.OPEN

    return isinstance(action, Pon | Chi | Ron)


def _inject_pass_calls(
    ctx: _ReplayRunContext,
    *,
    seating: _ReplaySeating,
    steps: list[ReplayStep],
    exclude_seats: frozenset[int] = frozenset(),
) -> None:
    """
    Inject synthetic PASS steps for pending call prompt seats.

    exclude_seats: seats to skip because input events answer for them: the
    seat of the next input event when it is a call response, plus the seats
    of the rons that directly follow a ron.
    """
    prompt = ctx.runtime.state.round_state.pending_call_prompt
    if prompt is None:
        return

    seats_to_pass = sorted(prompt.pending_seats - exclude_seats)
    for seat in seats_to_pass:
        # Re-read prompt state: earlier PASS may have resolved the prompt entirely
        if ctx.runtime.state.round_state.pending_call_prompt is None:
            break

        pass_event = ReplayInputEvent(player_name=seating.player_by_seat[seat], action=Pass())
        _run_step(ctx, steps=steps, seat=seat, input_event=pass_event, synthetic=True)
