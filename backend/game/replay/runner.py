from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.logic.enums import GameAction, GamePhase, WaitKind
from game.logic.events import EventType
from game.logic.mahjong_service import MahjongGameService
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

    from game.logic.runtime import GameRuntime
    from game.logic.service import GameService


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
        resolved_opts = ReplayOptions(
            game_id=f"replay-{uuid.uuid4().hex}",
            strict=resolved_opts.strict,
            auto_confirm_rounds=resolved_opts.auto_confirm_rounds,
            auto_pass_calls=resolved_opts.auto_pass_calls,
            max_steps=resolved_opts.max_steps,
        )

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
    runtime = start.runtime
    ctx = _ReplayRunContext(service=service, opts=opts, events=replay.events, runtime=runtime)

    initial_state = runtime.state
    seat_by_player = dict(zip(replay.player_names, start.seats, strict=True))
    seating = _ReplaySeating(
        seat_by_player=seat_by_player,
        player_by_seat={seat: name for name, seat in seat_by_player.items()},
    )

    steps: list[ReplayStep] = []
    step_count = 0
    for index, input_event in enumerate(replay.events):
        _check_step_limit(step_count, opts.max_steps)
        if runtime.state.game_phase == GamePhase.FINISHED:
            if opts.strict:
                raise ReplayInputAfterGameEndError(
                    f"Input remains after game end at step {step_count}: {input_event}",
                )

            break

        step_count = _maybe_confirm_round(ctx, seating=seating, steps=steps, step_count=step_count)

        if opts.auto_pass_calls:
            step_count = _handle_auto_pass_for_input(
                ctx,
                index=index,
                seating=seating,
                steps=steps,
                step_count=step_count,
            )

        # Auto-pass resolution may end the round (e.g. exhaustive draw after
        # the last call prompt resolves). Re-check for round advance.
        step_count = _maybe_confirm_round(ctx, seating=seating, steps=steps, step_count=step_count)

        # Re-check game phase: auto-pass or round confirmation may have ended the game
        if runtime.state.game_phase == GamePhase.FINISHED:
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

    return ReplayTrace(
        seed=replay.seed,
        rng_version=replay.rng_version,
        seat_by_player=seat_by_player,
        startup_events=tuple(start.events),
        initial_state=initial_state,
        steps=tuple(steps),
        final_state=runtime.state,
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
    state_before = ctx.runtime.state

    events = ctx.service.handle_action(
        ctx.runtime,
        seat=seat,
        action=input_event.action,
        data=dict(input_event.data),
    ).events

    if ctx.opts.strict:
        errors = [e for e in events if e.event == EventType.ERROR]
        if errors:
            raise ReplayError(step_index=step_count, event=input_event, errors=errors)

    steps.append(
        ReplayStep(
            input_event=input_event,
            emitted_events=tuple(events),
            state_before=state_before,
            state_after=ctx.runtime.state,
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
    if ctx.opts.auto_confirm_rounds and ctx.service.get_awaiting(ctx.runtime).kind == WaitKind.ROUND_ADVANCE:
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
    Inject synthetic CONFIRM_ROUND steps for all pending players, in seat order.
    """
    for seat in sorted(ctx.service.get_awaiting(ctx.runtime).seats):
        _check_step_limit(step_count, ctx.opts.max_steps)
        player_name = seating.player_by_seat[seat]

        synthetic_before = ctx.runtime.state
        confirm_events = ctx.service.handle_action(
            ctx.runtime, seat=seat, action=GameAction.CONFIRM_ROUND, data={}
        ).events

        if ctx.opts.strict:
            errors = [e for e in confirm_events if e.event == EventType.ERROR]
            if errors:
                synthetic_event = ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.CONFIRM_ROUND,
                )
                raise ReplayError(step_index=step_count, event=synthetic_event, errors=errors)

        steps.append(
            ReplayStep(
                input_event=ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.CONFIRM_ROUND,
                ),
                synthetic=True,
                emitted_events=tuple(confirm_events),
                state_before=synthetic_before,
                state_after=ctx.runtime.state,
            ),
        )
        step_count += 1

    return step_count


def _handle_auto_pass_for_input(
    ctx: _ReplayRunContext,
    *,
    index: int,
    seating: _ReplaySeating,
    steps: list[ReplayStep],
    step_count: int,
) -> int:
    """
    Handle auto-pass logic before processing the input event at index.

    If a call prompt is pending:
    - If the input is a call response from a pending seat, skip that seat
      (it will be processed normally) and auto-pass the remaining seats.
      A ron also spares the seats of the rons that directly follow it in the
      input: a double or triple ron is recorded as consecutive CALL_RON inputs
      answering the same prompt.
    - Otherwise, auto-pass all pending seats first.
    """
    prompt = ctx.runtime.state.round_state.pending_call_prompt
    if prompt is None:
        return step_count

    events = ctx.events
    input_event = events[index]
    input_seat = seating.seat_by_player[input_event.player_name]
    is_call_response = input_event.action in _CALL_RESPONSE_ACTIONS and input_seat in prompt.pending_seats
    if not is_call_response:
        return _inject_pass_calls(ctx, seating=seating, steps=steps, step_count=step_count)

    responding_seats = {input_seat}
    if input_event.action == GameAction.CALL_RON:
        for later_index in range(index + 1, len(events)):
            later_event = events[later_index]
            if later_event.action != GameAction.CALL_RON:
                break

            responding_seats.add(seating.seat_by_player[later_event.player_name])

    return _inject_pass_calls(
        ctx,
        seating=seating,
        steps=steps,
        step_count=step_count,
        exclude_seats=frozenset(responding_seats),
    )


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

    exclude_seats: seats to skip because input events answer for them: the
    seat of the next input event when it is a call response, plus the seats
    of the rons that directly follow a ron.
    """
    prompt = ctx.runtime.state.round_state.pending_call_prompt
    if prompt is None:
        return step_count

    seats_to_pass = sorted(prompt.pending_seats - exclude_seats)
    for seat in seats_to_pass:
        # Re-read prompt state: earlier PASS may have resolved the prompt entirely
        if ctx.runtime.state.round_state.pending_call_prompt is None:
            break

        _check_step_limit(step_count, ctx.opts.max_steps)
        player_name = seating.player_by_seat[seat]

        synthetic_before = ctx.runtime.state
        pass_events = ctx.service.handle_action(ctx.runtime, seat=seat, action=GameAction.PASS, data={}).events

        if ctx.opts.strict:
            errors = [e for e in pass_events if e.event == EventType.ERROR]
            if errors:
                synthetic_event = ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.PASS,
                )
                raise ReplayError(step_index=step_count, event=synthetic_event, errors=errors)

        steps.append(
            ReplayStep(
                input_event=ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.PASS,
                ),
                synthetic=True,
                emitted_events=tuple(pass_events),
                state_before=synthetic_before,
                state_after=ctx.runtime.state,
            ),
        )
        step_count += 1

    return step_count
