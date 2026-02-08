"""
Replay runner: feeds recorded actions through ReplayServiceProtocol and captures trace.

Uses MahjongGameService as a black-box engine through its public API.
Bot determinism contract: bot strategies must be deterministic given the same state.
Currently only TSUMOGIRI exists (always discards last drawn tile).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from game.logic.enums import GameAction, GamePhase
from game.logic.events import ErrorEvent, EventType, ServiceEvent
from game.logic.mahjong_service import MahjongGameService
from game.logic.settings import GameSettings
from game.logic.state import MahjongGameState
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


class ReplayServiceProtocol(Protocol):
    """Replay-facing protocol for game service interaction."""

    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: float | None = None,
        settings: GameSettings | None = None,
    ) -> list[ServiceEvent]: ...
    async def handle_action(
        self, game_id: str, player_name: str, action: GameAction, data: dict[str, Any]
    ) -> list[ServiceEvent]: ...
    def cleanup_game(self, game_id: str) -> None: ...
    def get_game_state(self, game_id: str) -> MahjongGameState | None: ...
    def is_round_advance_pending(self, game_id: str) -> bool: ...
    def get_pending_round_advance_human_names(self, game_id: str) -> list[str]: ...


@dataclass(frozen=True)
class ReplayOptions:
    """Configuration for a replay run."""

    game_id: str
    strict: bool
    auto_confirm_rounds: bool
    max_steps: int


def _default_service_factory() -> ReplayServiceProtocol:
    return MahjongGameService(auto_cleanup=False)


def run_replay(  # noqa: PLR0913
    replay: ReplayInput,
    *,
    game_id: str | None = None,
    strict: bool = True,
    auto_confirm_rounds: bool = True,
    max_steps: int = 10_000,
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
            run_replay_async(
                replay,
                game_id=game_id,
                strict=strict,
                auto_confirm_rounds=auto_confirm_rounds,
                max_steps=max_steps,
                service_factory=service_factory,
            )
        )
    raise RuntimeError("run_replay() cannot be used in async context; use await run_replay_async(...)")


async def run_replay_async(  # noqa: PLR0913
    replay: ReplayInput,
    *,
    game_id: str | None = None,
    strict: bool = True,
    auto_confirm_rounds: bool = True,
    max_steps: int = 10_000,
    service_factory: Callable[[], ReplayServiceProtocol] | None = None,
) -> ReplayTrace:
    """
    Run a deterministic replay through the game service.

    Feeds replay input events through the service and captures a full trace
    with state_before/state_after for each transition.
    """
    opts = ReplayOptions(
        game_id=game_id or f"replay-{uuid.uuid4().hex}",
        strict=strict,
        auto_confirm_rounds=auto_confirm_rounds,
        max_steps=max_steps,
    )
    factory = service_factory or _default_service_factory
    service = factory()

    try:
        return await _execute_replay(service, replay, opts)
    finally:
        service.cleanup_game(opts.game_id)


async def _execute_replay(
    service: ReplayServiceProtocol,
    replay: ReplayInput,
    opts: ReplayOptions,
) -> ReplayTrace:
    """Core replay execution loop."""
    if opts.auto_confirm_rounds:
        _reject_manual_confirm_rounds(replay)

    startup_events = await service.start_game(opts.game_id, list(replay.player_names), seed=replay.seed)
    _check_startup_errors(startup_events, opts.strict)

    initial_state = _require_state(
        service,
        opts.game_id,
        "start_game completed but game state is missing",
    )
    seat_by_player = {player.name: player.seat for player in initial_state.round_state.players}

    steps: list[ReplayStep] = []
    step_count = 0

    for input_event in replay.events:
        _check_step_limit(step_count, opts.max_steps)
        current_state = _require_state(
            service,
            opts.game_id,
            "game state disappeared during replay execution",
        )

        if current_state.game_phase == GamePhase.FINISHED:
            if opts.strict:
                raise ReplayInputAfterGameEndError(
                    f"Input remains after game end at step {step_count}: {input_event}"
                )
            break

        if opts.auto_confirm_rounds and service.is_round_advance_pending(opts.game_id):
            step_count = await _inject_round_confirmations(
                service,
                opts.game_id,
                steps,
                step_count,
                opts,
            )
            _check_step_limit(step_count, opts.max_steps)

        step_count = await _process_input_event(
            service,
            input_event,
            steps,
            step_count,
            opts,
        )

    # Handle any trailing round advance after all input events are consumed
    if opts.auto_confirm_rounds and service.is_round_advance_pending(opts.game_id):
        step_count = await _inject_round_confirmations(
            service,
            opts.game_id,
            steps,
            step_count,
            opts,
        )

    final_state = _require_state(service, opts.game_id, "replay finished but final state is missing")
    return ReplayTrace(
        seed=replay.seed,
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
        raise ValueError(
            f"ReplayInput.events contains CONFIRM_ROUND at indices {confirm_indices}, "
            "but auto_confirm_rounds=True. Either remove CONFIRM_ROUND events from "
            "the input or set auto_confirm_rounds=False."
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
    service: ReplayServiceProtocol,
    input_event: ReplayInputEvent,
    steps: list[ReplayStep],
    step_count: int,
    opts: ReplayOptions,
) -> int:
    """Process one human input event and append to steps."""
    state_before = _require_state(
        service,
        opts.game_id,
        "game state disappeared before replay action",
    )

    events = await service.handle_action(
        opts.game_id,
        input_event.player_name,
        input_event.action,
        dict(input_event.data),
    )

    if opts.strict:
        errors = [e for e in events if e.event == EventType.ERROR]
        if errors:
            raise ReplayError(step_count, input_event, errors)

    state_after = _require_state(
        service,
        opts.game_id,
        "game state disappeared after replay action",
    )
    steps.append(
        ReplayStep(
            input_event=input_event,
            emitted_events=tuple(events),
            state_before=state_before,
            state_after=state_after,
        )
    )
    return step_count + 1


async def _inject_round_confirmations(
    service: ReplayServiceProtocol,
    game_id: str,
    steps: list[ReplayStep],
    step_count: int,
    opts: ReplayOptions,
) -> int:
    """Inject synthetic CONFIRM_ROUND steps for all pending human players."""
    for human_name in service.get_pending_round_advance_human_names(game_id):
        _check_step_limit(step_count, opts.max_steps)

        synthetic_before = _require_state(
            service,
            game_id,
            "game state disappeared before synthetic confirm_round",
        )

        confirm_events = await service.handle_action(game_id, human_name, GameAction.CONFIRM_ROUND, {})

        if opts.strict:
            errors = [e for e in confirm_events if e.event == EventType.ERROR]
            if errors:
                synthetic_event = ReplayInputEvent(
                    player_name=human_name,
                    action=GameAction.CONFIRM_ROUND,
                )
                raise ReplayError(step_count, synthetic_event, errors)

        state_after = _require_state(
            service,
            game_id,
            "game state disappeared after synthetic confirm_round",
        )

        steps.append(
            ReplayStep(
                input_event=ReplayInputEvent(
                    player_name=human_name,
                    action=GameAction.CONFIRM_ROUND,
                ),
                synthetic=True,
                emitted_events=tuple(confirm_events),
                state_before=synthetic_before,
                state_after=state_after,
            )
        )
        step_count += 1

    return step_count
