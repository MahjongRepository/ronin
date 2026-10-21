from typing import TYPE_CHECKING, Any

import pytest

from game.logic.enums import CallType, GameAction, GameErrorCode, GamePhase
from game.logic.events import (
    BroadcastTarget,
    ErrorEvent,
    EventType,
    ServiceEvent,
)
from game.logic.exceptions import InvalidGameActionError
from game.logic.mahjong_service import MahjongGameService
from game.logic.rng import RNG_VERSION
from game.logic.state import MahjongGameState, PendingCallPrompt
from game.replay.loader import ReplayLoadError
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
    ReplayOptions,
    run_replay,
    run_replay_async,
)

if TYPE_CHECKING:
    from game.logic.settings import GameSettings

PLAYER_NAMES = ("Alice", "Bob", "Charlie", "Diana")
SEED = "a" * 192


def _build_replay(
    seed: str = SEED,
    player_names: tuple[str, str, str, str] = PLAYER_NAMES,
    actions: tuple[tuple[str, GameAction, dict[str, Any]], ...] = (),
) -> ReplayInput:
    events = tuple(ReplayInputEvent(player_name=name, action=action, data=data) for name, action, data in actions)
    return ReplayInput(seed=seed, player_names=player_names, events=events)


class _StubService:
    def __init__(self) -> None:
        self._inner = MahjongGameService(auto_cleanup=False)

    async def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> list[ServiceEvent]:
        return await self._inner.start_game(game_id, player_names, seed=seed, wall=wall)

    async def handle_action(
        self,
        game_id: str,
        player_name: str,
        action: GameAction,
        data: dict[str, Any],
    ) -> list[ServiceEvent]:
        return await self._inner.handle_action(game_id, player_name, action, data)

    def cleanup_game(self, game_id: str) -> None:
        self._inner.cleanup_game(game_id)

    def get_game_state(self, game_id: str) -> MahjongGameState | None:
        return self._inner.get_game_state(game_id)

    def is_round_advance_pending(self, game_id: str) -> bool:
        return self._inner.is_round_advance_pending(game_id)

    def get_pending_round_advance_player_names(self, game_id: str) -> list[str]:
        return self._inner.get_pending_round_advance_player_names(game_id)


async def _async_probe_current_player_discard() -> tuple[str, int]:
    svc = MahjongGameService(auto_cleanup=False)
    await svc.start_game("probe", list(PLAYER_NAMES), seed=SEED)
    state = svc.get_game_state("probe")
    assert state is not None
    seat = state.round_state.current_player_seat
    player = state.round_state.players[seat]
    svc.cleanup_game("probe")
    return player.name, player.tiles[-1]


async def test_run_replay_async__when_discard_input__should_trace_discard_step():
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


async def test_run_replay_async__when_strict_and_action_invalid__should_raise_replay_error():
    replay = _build_replay(actions=(("Bob", GameAction.DISCARD, {"tile_id": 999}),))

    with pytest.raises(ReplayError) as exc_info:
        await run_replay_async(replay)
    assert exc_info.value.step_index == 0
    assert exc_info.value.event.player_name == "Bob"


async def test_run_replay_async__when_non_strict_and_action_invalid__should_record_error_step():
    replay = _build_replay(actions=(("Bob", GameAction.DISCARD, {"tile_id": 999}),))

    trace = await run_replay_async(replay, ReplayOptions(strict=False))
    assert len(trace.steps) == 1
    error_events = [e for e in trace.steps[0].emitted_events if e.event == EventType.ERROR]
    assert len(error_events) == 1


async def test_run_replay_async__when_service_raises_invalid_action__should_raise_or_record_by_strictness():

    class RaisingService(_StubService):
        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            raise InvalidGameActionError(action="discard", seat=0, reason="test error")

    replay = _build_replay(actions=(("Alice", GameAction.DISCARD, {"tile_id": 0}),))

    # Strict mode: raises ReplayError
    with pytest.raises(ReplayError) as exc_info:
        await run_replay_async(replay, service_factory=RaisingService)
    assert exc_info.value.step_index == 0

    # Non-strict mode: converts to error event step
    trace = await run_replay_async(replay, ReplayOptions(strict=False), service_factory=RaisingService)
    assert len(trace.steps) == 1
    error_events = [e for e in trace.steps[0].emitted_events if e.event == EventType.ERROR]
    assert len(error_events) == 1
    assert error_events[0].data.code == GameErrorCode.INVALID_ACTION


async def test_run_replay_async__when_service_factory_given__should_use_it_and_clean_up():
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


async def test_run_replay_async__when_replay_succeeds_or_fails__should_clean_up_game():
    cleanup_calls: list[str] = []

    class TrackingService(MahjongGameService):
        def cleanup_game(self, game_id: str) -> None:
            cleanup_calls.append(game_id)
            super().cleanup_game(game_id)

    # Success case
    replay = _build_replay()
    await run_replay_async(
        replay,
        service_factory=lambda: TrackingService(auto_cleanup=False),
    )
    assert len(cleanup_calls) == 1

    # Error case
    cleanup_calls.clear()
    replay = _build_replay(actions=(("Bob", GameAction.DISCARD, {"tile_id": 999}),))
    with pytest.raises(ReplayError):
        await run_replay_async(
            replay,
            service_factory=lambda: TrackingService(auto_cleanup=False),
        )
    assert len(cleanup_calls) == 1


def test_run_replay__should_return_trace_with_seed():
    replay = _build_replay()
    trace = run_replay(replay)
    assert isinstance(trace, ReplayTrace)
    assert trace.seed == SEED


async def test_run_replay__when_called_in_async_context__should_raise():
    replay = _build_replay()
    with pytest.raises(RuntimeError, match="cannot be used in async context"):
        run_replay(replay)


async def test_run_replay_async__when_max_steps_zero__should_raise_step_limit_error():
    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))
    with pytest.raises(ReplayStepLimitError, match="exceeded 0 steps"):
        await run_replay_async(replay, ReplayOptions(max_steps=0))


async def test_run_replay_async__should_map_every_player_to_a_seat():
    replay = _build_replay()
    trace = await run_replay_async(replay)
    assert len(trace.seat_by_player) == 4
    for name in PLAYER_NAMES:
        assert name in trace.seat_by_player
        assert trace.seat_by_player[name] in range(4)


async def test_run_replay_async__when_strict_and_input_after_game_end__should_raise():

    class FinishedService(_StubService):
        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
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
        await run_replay_async(replay, service_factory=FinishedService)


async def test_run_replay_async__when_non_strict_and_input_after_game_end__should_skip_input():

    class FinishedService(_StubService):
        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            state = self._inner.get_game_state(game_id)
            assert state is not None
            self._inner._games[game_id] = state.model_copy(
                update={"game_phase": GamePhase.FINISHED},
            )
            return events

    replay = _build_replay(actions=(("Alice", GameAction.DISCARD, {"tile_id": 0}),))
    trace = await run_replay_async(replay, ReplayOptions(strict=False), service_factory=FinishedService)
    assert trace.final_state.game_phase == GamePhase.FINISHED
    assert len(trace.steps) == 0


async def test_run_replay_async__when_strict_and_startup_emits_error__should_raise_startup_error():

    class ErrorStartupService(_StubService):
        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            error_event = ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(
                    code=GameErrorCode.GAME_ERROR,
                    message="test startup error",
                    target="all",
                ),
                target=BroadcastTarget(),
            )
            return [error_event, *events]

    replay = _build_replay()
    with pytest.raises(ReplayStartupError, match="test startup error"):
        await run_replay_async(replay, service_factory=ErrorStartupService)


async def test_run_replay_async__when_non_strict_and_startup_emits_error__should_return_trace():

    class ErrorStartupService(_StubService):
        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            error_event = ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(
                    code=GameErrorCode.GAME_ERROR,
                    message="test startup error",
                    target="all",
                ),
                target=BroadcastTarget(),
            )
            return [error_event, *events]

    replay = _build_replay()
    trace = await run_replay_async(replay, ReplayOptions(strict=False), service_factory=ErrorStartupService)
    assert isinstance(trace, ReplayTrace)


async def test_run_replay_async__when_game_state_disappears__should_raise_invariant_error():

    class DisappearingStateService(_StubService):
        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            self._inner.cleanup_game(game_id)
            return []

    replay = _build_replay(actions=(("Alice", GameAction.DISCARD, {"tile_id": 0}),))
    with pytest.raises(ReplayInvariantError, match="game state disappeared after replay action"):
        await run_replay_async(replay, ReplayOptions(strict=False), service_factory=DisappearingStateService)


async def test_round_confirmation__when_round_advance_pending__should_inject_synthetic_confirm_steps():

    class RoundAdvanceService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._advance_pending = False
            self._advance_players: list[str] = []

        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> list[ServiceEvent]:
            self._advance_players = list(player_names)
            return await super().start_game(game_id, player_names, seed=seed)

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            if action == GameAction.CONFIRM_ROUND:
                if player_name in self._advance_players:
                    self._advance_players.remove(player_name)
                if not self._advance_players:
                    self._advance_pending = False
                return []
            events = await super().handle_action(game_id, player_name, action, data)
            self._advance_pending = True
            state = self._inner.get_game_state(game_id)
            assert state is not None
            self._advance_players = [p.name for p in state.round_state.players]
            return events

        def is_round_advance_pending(self, game_id: str) -> bool:
            return self._advance_pending

        def get_pending_round_advance_player_names(self, game_id: str) -> list[str]:
            return list(self._advance_players) if self._advance_pending else []

    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(
        actions=(
            (name, GameAction.DISCARD, {"tile_id": tile}),
            (name, GameAction.DISCARD, {"tile_id": tile}),
        ),
    )

    trace = await run_replay_async(replay, ReplayOptions(strict=False), service_factory=RoundAdvanceService)

    synthetic_confirm_steps = [
        s for s in trace.steps if s.synthetic and s.input_event.action == GameAction.CONFIRM_ROUND
    ]
    assert len(synthetic_confirm_steps) > 0


async def test_round_confirmation__when_strict_and_confirm_returns_error__should_raise_replay_error():

    class ConfirmErrorService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._advance_pending = False

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
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
                        target=BroadcastTarget(),
                    ),
                ]
            events = await super().handle_action(game_id, player_name, action, data)
            self._advance_pending = True
            return events

        def is_round_advance_pending(self, game_id: str) -> bool:
            return self._advance_pending

        def get_pending_round_advance_player_names(self, game_id: str) -> list[str]:
            return ["Alice"] if self._advance_pending else []

    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(
        actions=(
            (name, GameAction.DISCARD, {"tile_id": tile}),
            (name, GameAction.DISCARD, {"tile_id": tile}),
        ),
    )

    with pytest.raises(ReplayError, match="confirm_round error"):
        await run_replay_async(replay, service_factory=ConfirmErrorService)


async def test_step_limit__when_synthetic_confirms_reach_max_steps__should_raise_before_next_input():

    class RoundAdvanceService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._advance_pending = False

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            if action == GameAction.CONFIRM_ROUND:
                self._advance_pending = False
                return []
            events = await super().handle_action(game_id, player_name, action, data)
            self._advance_pending = True
            return events

        def is_round_advance_pending(self, game_id: str) -> bool:
            return self._advance_pending

        def get_pending_round_advance_player_names(self, game_id: str) -> list[str]:
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
        ),
    )

    with pytest.raises(ReplayStepLimitError, match="exceeded 3 steps"):
        await run_replay_async(replay, ReplayOptions(max_steps=3, strict=False), service_factory=RoundAdvanceService)


async def test_auto_confirm_rounds__when_input_has_confirm_round__should_raise_load_error():
    replay = _build_replay(actions=(("Alice", GameAction.CONFIRM_ROUND, {}),))

    with pytest.raises(ReplayLoadError, match=r"CONFIRM_ROUND.*auto_confirm_rounds=True"):
        await run_replay_async(replay)


async def test_auto_confirm_rounds__when_disabled_and_input_has_confirm_round__should_run_it_as_game_action():
    replay = _build_replay(actions=(("Alice", GameAction.CONFIRM_ROUND, {}),))

    # This should not raise ValueError; it may raise ReplayError due to
    # "no round pending confirmation" but that's a game-logic error, not validation.
    with pytest.raises(ReplayError):
        await run_replay_async(replay, ReplayOptions(auto_confirm_rounds=False))


async def test_auto_pass_calls__when_call_prompt_pending__should_inject_pass_for_other_seats():

    class CallPromptService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._inject_prompt = False

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            if action == GameAction.PASS:
                # Resolve the call prompt by removing it from state
                state = self._inner.get_game_state(game_id)
                assert state is not None
                prompt = state.round_state.pending_call_prompt
                if prompt is not None:
                    new_pending = prompt.pending_seats - {
                        next(p.seat for p in state.round_state.players if p.name == player_name),
                    }
                    new_prompt = prompt.model_copy(update={"pending_seats": new_pending}) if new_pending else None
                    new_round = state.round_state.model_copy(
                        update={"pending_call_prompt": new_prompt},
                    )
                    self._inner._games[game_id] = state.model_copy(
                        update={"round_state": new_round},
                    )
                return []

            events = await super().handle_action(game_id, player_name, action, data)
            # Inject a fake call prompt after a discard
            if action == GameAction.DISCARD:
                state = self._inner.get_game_state(game_id)
                assert state is not None
                seat = next(p.seat for p in state.round_state.players if p.name == player_name)
                other_seats = frozenset(p.seat for p in state.round_state.players if p.seat != seat)
                prompt = PendingCallPrompt(
                    call_type=CallType.MELD,
                    tile_id=0,
                    from_seat=seat,
                    pending_seats=other_seats,
                    callers=tuple(other_seats),
                )
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": prompt},
                )
                self._inner._games[game_id] = state.model_copy(
                    update={"round_state": new_round},
                )
            return events

    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    trace = await run_replay_async(
        replay,
        ReplayOptions(strict=False),
        service_factory=CallPromptService,
    )

    synthetic_steps = [s for s in trace.steps if s.synthetic]
    assert len(synthetic_steps) == 3  # 3 other players auto-passed
    for step in synthetic_steps:
        assert step.input_event.action == GameAction.PASS


async def test_auto_pass_calls__when_input_has_pass__should_raise_load_error():
    replay = _build_replay(actions=(("Alice", GameAction.PASS, {}),))

    with pytest.raises(ReplayLoadError, match=r"PASS.*auto_pass_calls=True"):
        await run_replay_async(replay)


async def test_auto_pass_calls__when_disabled_and_input_has_pass__should_run_it_as_game_action():
    replay = _build_replay(actions=(("Alice", GameAction.PASS, {}),))

    # This should not raise ValueError; it may raise ReplayError due to
    # "no call prompt pending" but that's a game-logic error, not validation.
    with pytest.raises(ReplayError):
        await run_replay_async(
            replay,
            ReplayOptions(auto_pass_calls=False),
        )


async def test_auto_pass_calls__when_player_responds_to_prompt__should_pass_only_the_others():
    # Discover actual seat assignments (seed-dependent)
    svc_probe = MahjongGameService(auto_cleanup=False)
    await svc_probe.start_game("probe-seats", list(PLAYER_NAMES), seed=SEED)
    probe_state = svc_probe.get_game_state("probe-seats")
    assert probe_state is not None
    name_to_seat = {p.name: p.seat for p in probe_state.round_state.players}
    svc_probe.cleanup_game("probe-seats")

    # Pick two seats: pon_player calls PON, auto_passed_player should be auto-passed
    pon_player = "Bob"
    auto_passed_player = "Charlie"
    discarder = "Alice"
    pon_seat = name_to_seat[pon_player]
    pass_seat = name_to_seat[auto_passed_player]
    discarder_seat = name_to_seat[discarder]

    class CallResponseService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_calls: list[str] = []

        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            state = self._inner.get_game_state(game_id)
            assert state is not None
            prompt = PendingCallPrompt(
                call_type=CallType.MELD,
                tile_id=0,
                from_seat=discarder_seat,
                pending_seats=frozenset({pon_seat, pass_seat}),
                callers=(pon_seat, pass_seat),
            )
            new_round = state.round_state.model_copy(
                update={"pending_call_prompt": prompt},
            )
            self._inner._games[game_id] = state.model_copy(
                update={"round_state": new_round},
            )
            return events

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            if action == GameAction.PASS:
                self._pass_calls.append(player_name)
                state = self._inner.get_game_state(game_id)
                assert state is not None
                prompt = state.round_state.pending_call_prompt
                if prompt is not None:
                    seat = next(p.seat for p in state.round_state.players if p.name == player_name)
                    new_pending = prompt.pending_seats - {seat}
                    new_prompt = prompt.model_copy(update={"pending_seats": new_pending}) if new_pending else None
                    new_round = state.round_state.model_copy(
                        update={"pending_call_prompt": new_prompt},
                    )
                    self._inner._games[game_id] = state.model_copy(
                        update={"round_state": new_round},
                    )
                return []
            if action == GameAction.CALL_PON:
                state = self._inner.get_game_state(game_id)
                assert state is not None
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": None},
                )
                self._inner._games[game_id] = state.model_copy(
                    update={"round_state": new_round},
                )
                return []
            return await super().handle_action(game_id, player_name, action, data)

    replay = _build_replay(actions=((pon_player, GameAction.CALL_PON, {"tile_id": 0}),))

    svc_instance = CallResponseService()
    trace = await run_replay_async(
        replay,
        ReplayOptions(strict=False),
        service_factory=lambda: svc_instance,
    )

    # auto_passed_player should have been auto-passed, but NOT pon_player
    assert svc_instance._pass_calls == [auto_passed_player]
    synthetic_steps = [s for s in trace.steps if s.synthetic]
    assert len(synthetic_steps) == 1
    assert synthetic_steps[0].input_event.player_name == auto_passed_player
    assert synthetic_steps[0].input_event.action == GameAction.PASS


async def test_auto_pass_calls__when_strict_and_synthetic_pass_errors__should_raise_replay_error():

    class PassErrorService(_StubService):
        def __init__(self) -> None:
            super().__init__()

        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            state = self._inner.get_game_state(game_id)
            assert state is not None
            # Inject a fake call prompt
            prompt = PendingCallPrompt(
                call_type=CallType.MELD,
                tile_id=0,
                from_seat=0,
                pending_seats=frozenset({1}),
                callers=(1,),
            )
            new_round = state.round_state.model_copy(
                update={"pending_call_prompt": prompt},
            )
            self._inner._games[game_id] = state.model_copy(
                update={"round_state": new_round},
            )
            return events

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            if action == GameAction.PASS:
                return [
                    ServiceEvent(
                        event=EventType.ERROR,
                        data=ErrorEvent(
                            code=GameErrorCode.INVALID_PASS,
                            message="synthetic pass error",
                            target="all",
                        ),
                        target=BroadcastTarget(),
                    ),
                ]
            return await super().handle_action(game_id, player_name, action, data)

    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    with pytest.raises(ReplayError, match="synthetic pass error"):
        await run_replay_async(
            replay,
            service_factory=PassErrorService,
        )


async def test_auto_pass_calls__when_prompt_pending_after_last_input__should_pass_remaining_seats():

    class TrailingPromptService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_calls: list[str] = []

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            if action == GameAction.PASS:
                self._pass_calls.append(player_name)
                state = self._inner.get_game_state(game_id)
                assert state is not None
                prompt = state.round_state.pending_call_prompt
                if prompt is not None:
                    seat = next(p.seat for p in state.round_state.players if p.name == player_name)
                    new_pending = prompt.pending_seats - {seat}
                    new_prompt = prompt.model_copy(update={"pending_seats": new_pending}) if new_pending else None
                    new_round = state.round_state.model_copy(
                        update={"pending_call_prompt": new_prompt},
                    )
                    self._inner._games[game_id] = state.model_copy(
                        update={"round_state": new_round},
                    )
                return []

            events = await super().handle_action(game_id, player_name, action, data)
            if action == GameAction.DISCARD:
                state = self._inner.get_game_state(game_id)
                assert state is not None
                seat = next(p.seat for p in state.round_state.players if p.name == player_name)
                other_seats = frozenset(p.seat for p in state.round_state.players if p.seat != seat)
                prompt = PendingCallPrompt(
                    call_type=CallType.MELD,
                    tile_id=0,
                    from_seat=seat,
                    pending_seats=other_seats,
                    callers=tuple(other_seats),
                )
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": prompt},
                )
                self._inner._games[game_id] = state.model_copy(
                    update={"round_state": new_round},
                )
            return events

    name, tile = await _async_probe_current_player_discard()
    # Single discard is the only input; the trailing block handles the prompt
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    svc_instance = TrailingPromptService()
    trace = await run_replay_async(
        replay,
        ReplayOptions(strict=False, auto_confirm_rounds=False),
        service_factory=lambda: svc_instance,
    )

    # The in-loop auto-pass does NOT fire (no subsequent input event to trigger it).
    # The trailing block after the loop injects PASS for all 3 other seats.
    synthetic_steps = [s for s in trace.steps if s.synthetic]
    assert len(synthetic_steps) == 3
    for step in synthetic_steps:
        assert step.input_event.action == GameAction.PASS
    assert len(svc_instance._pass_calls) == 3


async def test_run_replay_async__when_replay_has_rng_version__should_carry_it_to_trace():
    custom_version = "test-rng-v99"
    replay = _build_replay()
    replay = replay.model_copy(update={"rng_version": custom_version})
    trace = await run_replay_async(replay)
    assert trace.rng_version == custom_version
    assert trace.rng_version != RNG_VERSION


async def test_auto_pass_calls__when_strict_and_game_ends_during_pass__should_raise_input_after_game_end():

    class GameEndingPassService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_count = 0

        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            state = self._inner.get_game_state(game_id)
            assert state is not None
            # Inject a call prompt pending on seat 1
            prompt = PendingCallPrompt(
                call_type=CallType.MELD,
                tile_id=0,
                from_seat=0,
                pending_seats=frozenset({1}),
                callers=(1,),
            )
            new_round = state.round_state.model_copy(
                update={"pending_call_prompt": prompt},
            )
            self._inner._games[game_id] = state.model_copy(
                update={"round_state": new_round},
            )
            return events

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            if action == GameAction.PASS:
                self._pass_count += 1
                state = self._inner.get_game_state(game_id)
                assert state is not None
                # Resolve prompt and end the game
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": None},
                )
                self._inner._games[game_id] = state.model_copy(
                    update={
                        "round_state": new_round,
                        "game_phase": GamePhase.FINISHED,
                    },
                )
                return []
            return await super().handle_action(game_id, player_name, action, data)

    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    with pytest.raises(ReplayInputAfterGameEndError, match="Input remains after game end"):
        await run_replay_async(
            replay,
            service_factory=GameEndingPassService,
        )


async def test_auto_pass_calls__when_non_strict_and_game_ends_during_pass__should_skip_later_inputs():

    class GameEndingPassService(_StubService):
        def __init__(self) -> None:
            super().__init__()

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            if action == GameAction.PASS:
                state = self._inner.get_game_state(game_id)
                assert state is not None
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": None},
                )
                self._inner._games[game_id] = state.model_copy(
                    update={
                        "round_state": new_round,
                        "game_phase": GamePhase.FINISHED,
                    },
                )
                return []

            events = await super().handle_action(game_id, player_name, action, data)

            if action == GameAction.DISCARD:
                state = self._inner.get_game_state(game_id)
                assert state is not None
                seat = next(p.seat for p in state.round_state.players if p.name == player_name)
                other_seats = frozenset(p.seat for p in state.round_state.players if p.seat != seat)
                prompt = PendingCallPrompt(
                    call_type=CallType.MELD,
                    tile_id=0,
                    from_seat=seat,
                    pending_seats=other_seats,
                    callers=tuple(other_seats),
                )
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": prompt},
                )
                self._inner._games[game_id] = state.model_copy(
                    update={"round_state": new_round},
                )
            return events

    name, tile = await _async_probe_current_player_discard()
    # Two discards, but game ends during auto-pass after first discard
    replay = _build_replay(
        actions=(
            (name, GameAction.DISCARD, {"tile_id": tile}),
            (name, GameAction.DISCARD, {"tile_id": tile}),
        ),
    )

    trace = await run_replay_async(
        replay,
        ReplayOptions(strict=False),
        service_factory=GameEndingPassService,
    )
    assert trace.final_state.game_phase == GamePhase.FINISHED
    # First discard processed, then auto-pass ends game, second discard skipped
    non_synthetic = [s for s in trace.steps if not s.synthetic]
    assert len(non_synthetic) == 1
    assert non_synthetic[0].input_event.action == GameAction.DISCARD


async def test_auto_pass_calls__when_prompt_resolves_after_first_pass__should_stop_passing():

    class EarlyResolveService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_count = 0

        async def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> list[ServiceEvent]:
            events = await super().start_game(game_id, player_names, seed=seed)
            state = self._inner.get_game_state(game_id)
            assert state is not None
            prompt = PendingCallPrompt(
                call_type=CallType.MELD,
                tile_id=0,
                from_seat=0,
                pending_seats=frozenset({1, 2}),
                callers=(1, 2),
            )
            new_round = state.round_state.model_copy(
                update={"pending_call_prompt": prompt},
            )
            self._inner._games[game_id] = state.model_copy(
                update={"round_state": new_round},
            )
            return events

        async def handle_action(
            self,
            game_id: str,
            player_name: str,
            action: GameAction,
            data: dict[str, Any],
        ) -> list[ServiceEvent]:
            if action == GameAction.PASS:
                self._pass_count += 1
                state = self._inner.get_game_state(game_id)
                assert state is not None
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": None},
                )
                self._inner._games[game_id] = state.model_copy(
                    update={"round_state": new_round},
                )
                return []
            if action == GameAction.DISCARD:
                # Use real discard but ensure no new prompt is created
                events = await super().handle_action(game_id, player_name, action, data)
                state = self._inner.get_game_state(game_id)
                assert state is not None
                if state.round_state.pending_call_prompt is not None:
                    new_round = state.round_state.model_copy(
                        update={"pending_call_prompt": None},
                    )
                    self._inner._games[game_id] = state.model_copy(
                        update={"round_state": new_round},
                    )
                return events
            return await super().handle_action(game_id, player_name, action, data)

    name, tile = await _async_probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    svc_instance = EarlyResolveService()
    trace = await run_replay_async(
        replay,
        ReplayOptions(strict=False),
        service_factory=lambda: svc_instance,
    )

    # Only 1 PASS should have been sent (prompt resolved after first, breaking loop)
    assert svc_instance._pass_count == 1
    synthetic_pass_steps = [s for s in trace.steps if s.synthetic and s.input_event.action == GameAction.PASS]
    assert len(synthetic_pass_steps) == 1
