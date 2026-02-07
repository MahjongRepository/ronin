"""Tests for replay runner: async/sync APIs, service protocol, lifecycle."""

from typing import Any

import pytest

from game.logic.enums import GameAction, GamePhase
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import MahjongGameState
from game.messaging.events import (
    ErrorEvent,
    EventType,
    GameErrorCode,
    ServiceEvent,
)
from game.replay.models import (
    ReplayError,
    ReplayInput,
    ReplayInputAfterGameEndError,
    ReplayInputEvent,
    ReplayInvariantError,
    ReplayStartupError,
    ReplayStepLimitError,
    ReplayTrace,
)
from game.replay.runner import (
    run_replay,
    run_replay_async,
)

PLAYER_NAMES = ("Alice", "Bob", "Charlie", "Diana")
SEED = 42.0


def _build_replay(
    seed: float = SEED,
    player_names: tuple[str, str, str, str] = PLAYER_NAMES,
    actions: tuple[tuple[str, GameAction, dict[str, Any]], ...] = (),
) -> ReplayInput:
    """Helper to build ReplayInput from tuples."""
    events = tuple(
        ReplayInputEvent(player_name=name, action=action, data=data) for name, action, data in actions
    )
    return ReplayInput(seed=seed, player_names=player_names, events=events)


class _StubService:
    """Base stub implementing ReplayServiceProtocol with a real inner service.

    Subclasses override specific methods to inject test behavior.
    """

    def __init__(self) -> None:
        self._inner = MahjongGameService(auto_cleanup=False)

    async def start_game(
        self, game_id: str, player_names: list[str], *, seed: float | None = None
    ) -> list[ServiceEvent]:
        return await self._inner.start_game(game_id, player_names, seed=seed)

    async def handle_action(
        self, game_id: str, player_name: str, action: GameAction, data: dict[str, Any]
    ) -> list[ServiceEvent]:
        return await self._inner.handle_action(game_id, player_name, action, data)

    def cleanup_game(self, game_id: str) -> None:
        self._inner.cleanup_game(game_id)

    def get_game_state(self, game_id: str) -> MahjongGameState | None:
        return self._inner.get_game_state(game_id)

    def is_round_advance_pending(self, game_id: str) -> bool:
        return self._inner.is_round_advance_pending(game_id)

    def get_pending_round_advance_human_names(self, game_id: str) -> list[str]:
        return self._inner.get_pending_round_advance_human_names(game_id)


async def _async_probe_current_player_discard() -> tuple[str, int]:
    """Async version of probe for current player name and valid tile."""
    svc = MahjongGameService(auto_cleanup=False)
    await svc.start_game("probe", list(PLAYER_NAMES), seed=SEED)
    state = svc.get_game_state("probe")
    assert state is not None
    seat = state.round_state.current_player_seat
    player = state.round_state.players[seat]
    svc.cleanup_game("probe")
    return player.name, player.tiles[-1]


async def test_run_replay_async_basic_discard():
    """run_replay_async starts a game and processes a single discard."""
    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    trace = await run_replay_async(replay)
    assert isinstance(trace, ReplayTrace)
    assert trace.seed == SEED
    assert len(trace.steps) >= 1
    assert trace.steps[0].input_event.player_name == name
    assert trace.steps[0].state_before is not None
    assert trace.steps[0].state_after is not None
    assert trace.steps[0].input_event.action == GameAction.DISCARD
    assert any(e.event == EventType.DISCARD for e in trace.steps[0].emitted_events)
    assert trace.steps[0].state_after != trace.steps[0].state_before


async def test_run_replay_async_each_step_has_state_before_and_after():
    """Every ReplayStep captures both state_before and state_after."""
    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    trace = await run_replay_async(replay)
    for step in trace.steps:
        assert isinstance(step.state_before, MahjongGameState)
        assert isinstance(step.state_after, MahjongGameState)


async def test_run_replay_async_strict_mode_error_detection():
    """Strict mode raises ReplayError on invalid actions."""
    replay = _build_replay(actions=(("Bob", GameAction.DISCARD, {"tile_id": 999}),))

    with pytest.raises(ReplayError) as exc_info:
        await run_replay_async(replay, strict=True)
    assert exc_info.value.step_index == 0
    assert exc_info.value.event.player_name == "Bob"


async def test_run_replay_async_service_factory():
    """Runner works with a custom protocol-compatible factory."""
    factory_called = False
    cleanup_called = False

    class WrappedService(_StubService):
        def __init__(self) -> None:
            nonlocal factory_called
            factory_called = True
            super().__init__()

        def cleanup_game(self, game_id: str) -> None:
            nonlocal cleanup_called
            cleanup_called = True
            super().cleanup_game(game_id)

    replay = _build_replay()
    trace = await run_replay_async(replay, service_factory=WrappedService)
    assert isinstance(trace, ReplayTrace)
    assert factory_called
    assert cleanup_called


async def test_run_replay_async_unique_game_ids():
    """Runner-generated game_id values do not collide across runs."""
    game_ids: set[str] = set()

    class IdCapturingService(MahjongGameService):
        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: float | None = None,
        ) -> list[ServiceEvent]:
            game_ids.add(game_id)
            return await super().start_game(game_id, player_names, seed=seed)

    replay = _build_replay()
    for _ in range(5):
        await run_replay_async(
            replay,
            service_factory=lambda: IdCapturingService(auto_cleanup=False),
        )

    assert len(game_ids) == 5


async def test_run_replay_async_cleanup_on_success():
    """Runner calls cleanup_game after successful replay."""
    cleanup_calls: list[str] = []

    class TrackingService(MahjongGameService):
        def cleanup_game(self, game_id: str) -> None:
            cleanup_calls.append(game_id)
            super().cleanup_game(game_id)

    replay = _build_replay()
    await run_replay_async(
        replay,
        service_factory=lambda: TrackingService(auto_cleanup=False),
    )
    assert len(cleanup_calls) == 1


async def test_run_replay_async_cleanup_on_error():
    """Runner calls cleanup_game even when an error is raised."""
    cleanup_calls: list[str] = []

    class TrackingService(MahjongGameService):
        def cleanup_game(self, game_id: str) -> None:
            cleanup_calls.append(game_id)
            super().cleanup_game(game_id)

    replay = _build_replay(actions=(("Bob", GameAction.DISCARD, {"tile_id": 999}),))

    with pytest.raises(ReplayError):
        await run_replay_async(
            replay,
            strict=True,
            service_factory=lambda: TrackingService(auto_cleanup=False),
        )
    assert len(cleanup_calls) == 1


def test_run_replay_sync():
    """run_replay works in sync context."""
    replay = _build_replay()
    trace = run_replay(replay)
    assert isinstance(trace, ReplayTrace)
    assert trace.seed == SEED


async def test_run_replay_sync_raises_in_async_context():
    """run_replay raises RuntimeError when called from async context."""
    replay = _build_replay()
    with pytest.raises(RuntimeError, match="cannot be used in async context"):
        run_replay(replay)


async def test_run_replay_async_max_steps_limit():
    """Runner raises ReplayStepLimitError when max_steps exceeded."""
    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))
    with pytest.raises(ReplayStepLimitError, match="exceeded 0 steps"):
        await run_replay_async(replay, max_steps=0)


async def test_run_replay_async_seat_by_player():
    """ReplayTrace includes seat_by_player mapping."""
    replay = _build_replay()
    trace = await run_replay_async(replay)
    assert len(trace.seat_by_player) == 4
    for name in PLAYER_NAMES:
        assert name in trace.seat_by_player
        assert trace.seat_by_player[name] in range(4)


async def test_run_replay_async_input_after_game_end_strict():
    """Strict mode raises ReplayInputAfterGameEndError on extra input after game end."""

    class FinishedService(_StubService):
        async def start_game(
            self, game_id: str, player_names: list[str], *, seed: float | None = None
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            state = self._inner.get_game_state(game_id)
            assert state is not None
            self._inner._games[game_id] = state.model_copy(
                update={"game_phase": GamePhase.FINISHED},
            )
            return events

    replay = _build_replay(actions=(("Alice", GameAction.DISCARD, {"tile_id": 0}),))
    with pytest.raises(ReplayInputAfterGameEndError, match="Input remains after game end"):
        await run_replay_async(replay, strict=True, service_factory=FinishedService)


async def test_run_replay_async_input_after_game_end_non_strict():
    """Non-strict mode stops cleanly on extra input after game end."""

    class FinishedService(_StubService):
        async def start_game(
            self, game_id: str, player_names: list[str], *, seed: float | None = None
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            state = self._inner.get_game_state(game_id)
            assert state is not None
            self._inner._games[game_id] = state.model_copy(
                update={"game_phase": GamePhase.FINISHED},
            )
            return events

    replay = _build_replay(actions=(("Alice", GameAction.DISCARD, {"tile_id": 0}),))
    trace = await run_replay_async(replay, strict=False, service_factory=FinishedService)
    assert trace.final_state.game_phase == GamePhase.FINISHED
    assert len(trace.steps) == 0


async def test_run_replay_async_startup_error_strict():
    """Strict mode raises ReplayStartupError when startup has errors."""

    class ErrorStartupService(_StubService):
        async def start_game(
            self, game_id: str, player_names: list[str], *, seed: float | None = None
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            error_event = ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(
                    code=GameErrorCode.GAME_ERROR,
                    message="test startup error",
                    target="all",
                ),
            )
            return [error_event, *events]

    replay = _build_replay()
    with pytest.raises(ReplayStartupError, match="test startup error"):
        await run_replay_async(replay, strict=True, service_factory=ErrorStartupService)


async def test_run_replay_async_startup_error_non_strict():
    """Non-strict mode ignores startup errors."""

    class ErrorStartupService(_StubService):
        async def start_game(
            self, game_id: str, player_names: list[str], *, seed: float | None = None
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            error_event = ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(
                    code=GameErrorCode.GAME_ERROR,
                    message="test startup error",
                    target="all",
                ),
            )
            return [error_event, *events]

    replay = _build_replay()
    trace = await run_replay_async(replay, strict=False, service_factory=ErrorStartupService)
    assert isinstance(trace, ReplayTrace)


async def test_run_replay_async_invariant_error_missing_state():
    """Runner raises ReplayInvariantError when game state disappears."""

    class DisappearingStateService(_StubService):
        async def handle_action(
            self,
            game_id: str,
            player_name: str,  # noqa: ARG002
            action: GameAction,  # noqa: ARG002
            data: dict[str, Any],  # noqa: ARG002
        ) -> list[ServiceEvent]:
            self._inner.cleanup_game(game_id)
            return []

    replay = _build_replay(actions=(("Alice", GameAction.DISCARD, {"tile_id": 0}),))
    with pytest.raises(ReplayInvariantError, match="game state disappeared after replay action"):
        await run_replay_async(replay, strict=False, service_factory=DisappearingStateService)


async def test_run_replay_async_round_advance_injection():
    """Runner injects synthetic CONFIRM_ROUND steps for pending round advances."""

    class RoundAdvanceService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._advance_pending = False
            self._advance_humans: list[str] = []

        async def start_game(
            self, game_id: str, player_names: list[str], *, seed: float | None = None
        ) -> list[ServiceEvent]:
            self._advance_humans = list(player_names)
            return await super().start_game(game_id, player_names, seed=seed)

        async def handle_action(
            self, game_id: str, player_name: str, action: GameAction, data: dict[str, Any]
        ) -> list[ServiceEvent]:
            if action == GameAction.CONFIRM_ROUND:
                if player_name in self._advance_humans:
                    self._advance_humans.remove(player_name)
                if not self._advance_humans:
                    self._advance_pending = False
                return []
            events = await super().handle_action(game_id, player_name, action, data)
            self._advance_pending = True
            state = self._inner.get_game_state(game_id)
            assert state is not None
            self._advance_humans = [p.name for p in state.round_state.players]
            return events

        def is_round_advance_pending(self, game_id: str) -> bool:  # noqa: ARG002
            return self._advance_pending

        def get_pending_round_advance_human_names(self, game_id: str) -> list[str]:  # noqa: ARG002
            return list(self._advance_humans) if self._advance_pending else []

    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(
        actions=(
            (name, GameAction.DISCARD, {"tile_id": tile}),
            (name, GameAction.DISCARD, {"tile_id": tile}),
        )
    )

    trace = await run_replay_async(replay, strict=False, service_factory=RoundAdvanceService)

    synthetic_steps = [s for s in trace.steps if s.synthetic]
    assert len(synthetic_steps) > 0
    for step in synthetic_steps:
        assert step.input_event.action == GameAction.CONFIRM_ROUND


async def test_run_replay_async_round_confirm_error_in_strict_mode():
    """Strict mode raises ReplayError when synthetic confirm_round returns errors."""

    class ConfirmErrorService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._advance_pending = False

        async def handle_action(
            self, game_id: str, player_name: str, action: GameAction, data: dict[str, Any]
        ) -> list[ServiceEvent]:
            if action == GameAction.CONFIRM_ROUND:
                return [
                    ServiceEvent(
                        event=EventType.ERROR,
                        data=ErrorEvent(
                            code=GameErrorCode.GAME_ERROR,
                            message="confirm_round error",
                            target="all",
                        ),
                    )
                ]
            events = await super().handle_action(game_id, player_name, action, data)
            self._advance_pending = True
            return events

        def is_round_advance_pending(self, game_id: str) -> bool:  # noqa: ARG002
            return self._advance_pending

        def get_pending_round_advance_human_names(self, game_id: str) -> list[str]:  # noqa: ARG002
            return ["Alice"] if self._advance_pending else []

    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(
        actions=(
            (name, GameAction.DISCARD, {"tile_id": tile}),
            (name, GameAction.DISCARD, {"tile_id": tile}),
        )
    )

    with pytest.raises(ReplayError, match="confirm_round error"):
        await run_replay_async(replay, strict=True, service_factory=ConfirmErrorService)


async def test_step_limit_enforced_after_round_confirmations():
    """Step limit is enforced after synthetic round confirmations complete, before the next user input.

    This specifically tests the post-injection check in _execute_replay (line 169),
    not the per-confirmation check inside _inject_round_confirmations.
    With 2 pending humans and max_steps=3: 1 discard + 2 confirms = 3 steps,
    which hits the limit after confirmations complete but before the second discard.
    """

    class RoundAdvanceService(_StubService):
        """Service that reports a round advance pending after the first action."""

        def __init__(self) -> None:
            super().__init__()
            self._advance_pending = False

        async def handle_action(
            self, game_id: str, player_name: str, action: GameAction, data: dict[str, Any]
        ) -> list[ServiceEvent]:
            if action == GameAction.CONFIRM_ROUND:
                self._advance_pending = False
                return []
            events = await super().handle_action(game_id, player_name, action, data)
            self._advance_pending = True
            return events

        def is_round_advance_pending(self, game_id: str) -> bool:  # noqa: ARG002
            return self._advance_pending

        def get_pending_round_advance_human_names(self, game_id: str) -> list[str]:  # noqa: ARG002
            return list(PLAYER_NAMES[:2]) if self._advance_pending else []

    name, tile = await _async_probe_current_player_discard()
    # First discard (step 0->1) triggers round advance; 2 synthetic confirms follow
    # (step 1->2, 2->3). With max_steps=3, the post-injection check catches
    # step_count=3 >= max_steps=3 after confirmations complete, before the
    # second discard is processed.
    replay = _build_replay(
        actions=(
            (name, GameAction.DISCARD, {"tile_id": tile}),
            (name, GameAction.DISCARD, {"tile_id": tile}),
        )
    )

    with pytest.raises(ReplayStepLimitError, match="exceeded 3 steps"):
        await run_replay_async(replay, max_steps=3, strict=False, service_factory=RoundAdvanceService)


async def test_reject_confirm_round_in_events_with_auto_confirm():
    """Runner rejects CONFIRM_ROUND events in input when auto_confirm_rounds=True."""
    replay = _build_replay(actions=(("Alice", GameAction.CONFIRM_ROUND, {}),))

    with pytest.raises(ValueError, match=r"CONFIRM_ROUND.*auto_confirm_rounds=True"):
        await run_replay_async(replay, auto_confirm_rounds=True)


async def test_allow_confirm_round_in_events_without_auto_confirm():
    """Runner allows CONFIRM_ROUND events in input when auto_confirm_rounds=False."""
    replay = _build_replay(actions=(("Alice", GameAction.CONFIRM_ROUND, {}),))

    # This should not raise ValueError; it may raise ReplayError due to
    # "no round pending confirmation" but that's a game-logic error, not validation.
    with pytest.raises(ReplayError):
        await run_replay_async(replay, auto_confirm_rounds=False, strict=True)
