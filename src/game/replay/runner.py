"""
Replay runner: feeds recorded actions through ReplayServiceProtocol and captures trace.

Uses MahjongGameService as a black-box engine through its public API.
AI player determinism contract: AI player strategies must be deterministic given the same state.
Currently only TSUMOGIRI exists (always discards last drawn tile).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from game.logic.enums import GameAction, GameErrorCode, GamePhase
from game.logic.events import BroadcastTarget, ErrorEvent, EventType, ServiceEvent
from game.logic.exceptions import InvalidGameActionError
from game.logic.mahjong_service import MahjongGameService
from game.replay.loader import ReplayLoadError
from game.replay.models import (
    ReplayError,
    ReplayInput,
    ReplayInputAfterGameEndError,
    ReplayInputEvent,
    ReplayInvariantError,
    ReplayStartupError,
    ReplayStep,
    ReplayStepLimitError,
    ReplayTrace,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from game.logic.settings import GameSettings
    from game.logic.state import MahjongGameState


class ReplayServiceProtocol(Protocol):
    """Replay-facing protocol for game service interaction."""

    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> list[ServiceEvent]: ...
    async def handle_action(
        self,
        game_id: str,
        player_name: str,
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]: ...
    def cleanup_game(self, game_id: str) -> None: ...
    def get_game_state(self, game_id: str) -> MahjongGameState | None: ...
    def is_round_advance_pending(self, game_id: str) -> bool: ...
    def get_pending_round_advance_player_names(self, game_id: str) -> list[str]: ...


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
    """Configuration for a replay run."""

    game_id: str = ""
    strict: bool = True
    auto_confirm_rounds: bool = True
    auto_pass_calls: bool = True
    max_steps: int = 10_000


@dataclass(frozen=True)
class _ReplayRunContext:
    """Bundle service + options for internal replay functions."""

    service: ReplayServiceProtocol
    opts: ReplayOptions


def _default_service_factory() -> ReplayServiceProtocol:
    return MahjongGameService(auto_cleanup=False)


def run_replay(
    replay: ReplayInput,
    opts: ReplayOptions | None = None,
    *,
    service_factory: Callable[[], ReplayServiceProtocol] | None = None,
) -> ReplayTrace:
    """
    Sync wrapper for non-async contexts.

    Raises RuntimeError if called inside an active event loop
    (use run_replay_async instead).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            run_replay_async(replay, opts, service_factory=service_factory),
        )
    raise RuntimeError("run_replay() cannot be used in async context; use await run_replay_async(...)")


async def run_replay_async(
    replay: ReplayInput,
    opts: ReplayOptions | None = None,
    *,
    service_factory: Callable[[], ReplayServiceProtocol] | None = None,
) -> ReplayTrace:
    """
    Run a deterministic replay through the game service.

    Feed replay input events through the service and capture a full trace
    with state_before/state_after for each transition.
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
        return await _execute_replay(ctx, replay)
    finally:
        service.cleanup_game(resolved_opts.game_id)


async def _execute_replay(
    ctx: _ReplayRunContext,
    replay: ReplayInput,
) -> ReplayTrace:
    """Core replay execution loop."""
    opts = ctx.opts
    service = ctx.service

    if opts.auto_confirm_rounds:
        _reject_manual_confirm_rounds(replay)
    if opts.auto_pass_calls:
        _reject_manual_pass(replay)

    startup_events = await service.start_game(
        opts.game_id,
        list(replay.player_names),
        seed=replay.seed,
        wall=list(replay.wall) if replay.wall is not None else None,
    )
    _check_startup_errors(startup_events, opts.strict)

    initial_state = _require_state(service, opts.game_id, "start_game completed but game state is missing")
    seat_by_player = {player.name: player.seat for player in initial_state.round_state.players}

    steps: list[ReplayStep] = []
    step_count = 0

    for input_event in replay.events:
        _check_step_limit(step_count, opts.max_steps)
        current_state = _require_state(service, opts.game_id, "game state disappeared during replay execution")

        if current_state.game_phase == GamePhase.FINISHED:
            if opts.strict:
                raise ReplayInputAfterGameEndError(
                    f"Input remains after game end at step {step_count}: {input_event}",
                )
            break

        step_count = await _maybe_confirm_round(ctx, steps, step_count)

        if opts.auto_pass_calls:
            step_count = await _handle_auto_pass_for_input(ctx, input_event, seat_by_player, steps, step_count)

        # Auto-pass resolution may end the round (e.g. exhaustive draw after
        # the last call prompt resolves). Re-check for round advance.
        step_count = await _maybe_confirm_round(ctx, steps, step_count)

        # Re-check game phase: auto-pass or round confirmation may have ended the game
        post_synthetic_state = _require_state(
            service,
            opts.game_id,
            "game state disappeared after synthetic steps",
        )
        if post_synthetic_state.game_phase == GamePhase.FINISHED:
            if opts.strict:
                raise ReplayInputAfterGameEndError(
                    f"Input remains after game end at step {step_count}: {input_event}",
                )
            break

        step_count = await _process_input_event(ctx, input_event, steps, step_count)

    # Handle any trailing call prompt after all input events are consumed
    if opts.auto_pass_calls:
        step_count = await _inject_pass_calls(ctx, steps, step_count)

    # Handle any trailing round advance after all input events are consumed
    step_count = await _maybe_confirm_round(ctx, steps, step_count)

    final_state = _require_state(service, opts.game_id, "replay finished but final state is missing")
    return ReplayTrace(
        seed=replay.seed,
        rng_version=replay.rng_version,
        seat_by_player=seat_by_player,
        startup_events=tuple(startup_events),
        initial_state=initial_state,
        steps=tuple(steps),
        final_state=final_state,
    )


def _check_startup_errors(events: list[ServiceEvent], strict: bool) -> None:  # noqa: FBT001
    if not strict:
        return
    errors = [e for e in events if e.event == EventType.ERROR]
    if errors:
        messages = [e.data.message for e in errors if isinstance(e.data, ErrorEvent)]
        raise ReplayStartupError(f"Startup errors: {messages}")


def _reject_manual_confirm_rounds(replay: ReplayInput) -> None:
    """Reject CONFIRM_ROUND events in input when auto_confirm_rounds is enabled.

    When auto_confirm_rounds=True, the runner injects synthetic CONFIRM_ROUND
    steps automatically. Manual CONFIRM_ROUND events in the input would conflict
    and produce duplicate confirmation errors.
    """
    confirm_indices = [i for i, event in enumerate(replay.events) if event.action == GameAction.CONFIRM_ROUND]
    if confirm_indices:
        raise ReplayLoadError(
            f"ReplayInput.events contains CONFIRM_ROUND at indices {confirm_indices}, "
            "but auto_confirm_rounds=True. Either remove CONFIRM_ROUND events from "
            "the input or set auto_confirm_rounds=False.",
        )


def _reject_manual_pass(replay: ReplayInput) -> None:
    """Reject PASS events in input when auto_pass_calls is enabled.

    When auto_pass_calls=True, the runner injects synthetic PASS steps
    automatically. Manual PASS events in the input would conflict and produce
    duplicate pass errors.
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
    service: ReplayServiceProtocol,
    game_id: str,
    message: str,
) -> MahjongGameState:
    state = service.get_game_state(game_id)
    if state is None:
        raise ReplayInvariantError(message)
    return state


async def _process_input_event(
    ctx: _ReplayRunContext,
    input_event: ReplayInputEvent,
    steps: list[ReplayStep],
    step_count: int,
) -> int:
    """Process one player input event and append to steps."""
    state_before = _require_state(ctx.service, ctx.opts.game_id, "game state disappeared before replay action")

    try:
        events = await ctx.service.handle_action(
            ctx.opts.game_id,
            input_event.player_name,
            input_event.action,
            dict(input_event.data),
        )
    except InvalidGameActionError as exc:
        error_event = ServiceEvent(
            event=EventType.ERROR,
            data=ErrorEvent(target="all", code=GameErrorCode.INVALID_ACTION, message=str(exc)),
            target=BroadcastTarget(),
        )
        if ctx.opts.strict:
            raise ReplayError(step_count, input_event, [error_event]) from exc
        events = [error_event]

    if ctx.opts.strict:
        errors = [e for e in events if e.event == EventType.ERROR]
        if errors:
            raise ReplayError(step_count, input_event, errors)

    state_after = _require_state(ctx.service, ctx.opts.game_id, "game state disappeared after replay action")
    steps.append(
        ReplayStep(
            input_event=input_event,
            emitted_events=tuple(events),
            state_before=state_before,
            state_after=state_after,
        ),
    )
    return step_count + 1


async def _maybe_confirm_round(
    ctx: _ReplayRunContext,
    steps: list[ReplayStep],
    step_count: int,
) -> int:
    """Inject round confirmations if a round advance is pending."""
    if ctx.opts.auto_confirm_rounds and ctx.service.is_round_advance_pending(ctx.opts.game_id):
        step_count = await _inject_round_confirmations(ctx, steps, step_count)
        _check_step_limit(step_count, ctx.opts.max_steps)
    return step_count


async def _inject_round_confirmations(
    ctx: _ReplayRunContext,
    steps: list[ReplayStep],
    step_count: int,
) -> int:
    """Inject synthetic CONFIRM_ROUND steps for all pending players."""
    game_id = ctx.opts.game_id
    for player_name in ctx.service.get_pending_round_advance_player_names(game_id):
        _check_step_limit(step_count, ctx.opts.max_steps)

        synthetic_before = _require_state(
            ctx.service,
            game_id,
            "game state disappeared before synthetic confirm_round",
        )

        confirm_events = await ctx.service.handle_action(game_id, player_name, GameAction.CONFIRM_ROUND, {})

        if ctx.opts.strict:
            errors = [e for e in confirm_events if e.event == EventType.ERROR]
            if errors:
                synthetic_event = ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.CONFIRM_ROUND,
                )
                raise ReplayError(step_count, synthetic_event, errors)

        state_after = _require_state(
            ctx.service,
            game_id,
            "game state disappeared after synthetic confirm_round",
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


async def _handle_auto_pass_for_input(
    ctx: _ReplayRunContext,
    input_event: ReplayInputEvent,
    seat_by_player: dict[str, int],
    steps: list[ReplayStep],
    step_count: int,
) -> int:
    """Handle auto-pass logic before processing an input event.

    If a call prompt is pending:
    - If the input is a call response from a pending seat, skip that seat
      (it will be processed normally) and auto-pass the remaining seats.
    - Otherwise, auto-pass all pending seats first.
    """
    state = _require_state(ctx.service, ctx.opts.game_id, "game state disappeared before auto-pass check")
    prompt = state.round_state.pending_call_prompt
    if prompt is None:
        return step_count

    input_seat = seat_by_player.get(input_event.player_name)
    is_call_response = (
        input_event.action in _CALL_RESPONSE_ACTIONS and input_seat is not None and input_seat in prompt.pending_seats
    )

    exclude_seats = frozenset({input_seat}) if is_call_response and input_seat is not None else frozenset()
    return await _inject_pass_calls(ctx, steps, step_count, exclude_seats=exclude_seats)


async def _inject_pass_calls(
    ctx: _ReplayRunContext,
    steps: list[ReplayStep],
    step_count: int,
    *,
    exclude_seats: frozenset[int] = frozenset(),
) -> int:
    """Inject synthetic PASS steps for pending call prompt seats.

    exclude_seats: seats to skip (e.g., the seat of the next input event
    that is itself a call response).
    """
    game_id = ctx.opts.game_id
    state = _require_state(ctx.service, game_id, "game state disappeared before auto-pass injection")
    prompt = state.round_state.pending_call_prompt
    if prompt is None:
        return step_count

    seat_to_name = {p.seat: p.name for p in state.round_state.players}
    seats_to_pass = sorted(prompt.pending_seats - exclude_seats)
    for seat in seats_to_pass:
        # Re-read prompt state: earlier PASS may have resolved the prompt entirely
        fresh_state = _require_state(ctx.service, game_id, "game state disappeared during auto-pass injection")
        if fresh_state.round_state.pending_call_prompt is None:
            break

        _check_step_limit(step_count, ctx.opts.max_steps)
        player_name = seat_to_name[seat]

        synthetic_before = _require_state(ctx.service, game_id, "game state disappeared before synthetic pass")

        pass_events = await ctx.service.handle_action(game_id, player_name, GameAction.PASS, {})

        if ctx.opts.strict:
            errors = [e for e in pass_events if e.event == EventType.ERROR]
            if errors:
                synthetic_event = ReplayInputEvent(
                    player_name=player_name,
                    action=GameAction.PASS,
                )
                raise ReplayError(step_count, synthetic_event, errors)

        state_after = _require_state(ctx.service, game_id, "game state disappeared after synthetic pass")

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
