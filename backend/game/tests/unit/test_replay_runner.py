from typing import TYPE_CHECKING, Any

import pytest

from game.logic.enums import GameAction, GameErrorCode, GamePhase, MeldCallType, PromptKind, WaitKind
from game.logic.events import (
    BroadcastTarget,
    ErrorEvent,
    EventType,
    SeatTarget,
    ServiceEvent,
)
from game.logic.exceptions import InvalidGameActionError
from game.logic.mahjong_service import MahjongGameService
from game.logic.rng import RNG_VERSION
from game.logic.service import Awaiting, GameUpdate
from game.logic.settings import GameSettings
from game.logic.state import Caller, MeldOption, PendingCallPrompt
from game.replay.loader import ReplayLoadError
from game.replay.models import (
    ReplayError,
    ReplayInput,
    ReplayInputAfterGameEndError,
    ReplayInputEvent,
    ReplayStepLimitError,
    ReplayTrace,
)
from game.replay.runner import (
    ReplayOptions,
    run_replay,
)

if TYPE_CHECKING:
    from game.logic.runtime import GameRuntime
    from game.logic.service import GameStart

PLAYER_NAMES = ("Alice", "Bob", "Charlie", "Diana")
SEED = "a" * 192
STUB_AWAITING = Awaiting(kind=WaitKind.TURN, seats=frozenset(), wait_id=0, round_number=0)


def _stub_update(events: list[ServiceEvent]) -> GameUpdate:
    return GameUpdate(events=events, awaiting=STUB_AWAITING)


def _round_advance_awaiting(seats: list[int]) -> Awaiting:
    return Awaiting(kind=WaitKind.ROUND_ADVANCE, seats=frozenset(seats), wait_id=0, round_number=0)


def _pon_caller(seat: int) -> Caller:
    return Caller(seat=seat, melds=(MeldOption(call_type=MeldCallType.PON),))


def _build_replay(
    seed: str = SEED,
    player_names: tuple[str, str, str, str] = PLAYER_NAMES,
    actions: tuple[tuple[str, GameAction, dict[str, Any]], ...] = (),
) -> ReplayInput:
    events = tuple(ReplayInputEvent(player_name=name, action=action, data=data) for name, action, data in actions)
    return ReplayInput(seed=seed, player_names=player_names, settings=GameSettings(), events=events)


class _StubService:
    def __init__(self) -> None:
        self._inner = MahjongGameService()

    def start_game(
        self,
        game_id: str,
        player_names: list[str],
        *,
        seed: str | None = None,
        settings: GameSettings | None = None,
        wall: list[int] | None = None,
    ) -> GameStart:
        return self._inner.start_game(game_id, player_names, seed=seed, wall=wall)

    def handle_action(
        self,
        runtime: GameRuntime,
        *,
        seat: int,
        action: GameAction,
        data: dict[str, Any],
    ) -> GameUpdate:
        return self._inner.handle_action(runtime, seat=seat, action=action, data=data)

    def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
        return self._inner.get_awaiting(runtime)


def _probe_current_player_discard() -> tuple[str, int]:
    state = MahjongGameService().start_game("probe", list(PLAYER_NAMES), seed=SEED).runtime.state
    seat = state.round_state.current_player_seat
    player = state.round_state.players[seat]
    return player.name, player.tiles[-1]


def _probe_waiting_player() -> str:
    state = MahjongGameService().start_game("probe", list(PLAYER_NAMES), seed=SEED).runtime.state
    seat = (state.round_state.current_player_seat + 1) % 4
    return state.round_state.players[seat].name


def test_run_replay__when_discard_input__should_trace_discard_step():
    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    trace = run_replay(replay)
    assert isinstance(trace, ReplayTrace)
    assert trace.seed == SEED
    assert len(trace.steps) >= 1
    assert trace.steps[0].input_event.player_name == name
    assert trace.steps[0].state_before is not None
    assert trace.steps[0].state_after is not None
    assert trace.steps[0].input_event.action == GameAction.DISCARD
    assert any(e.event == EventType.DISCARD for e in trace.steps[0].emitted_events)
    assert trace.steps[0].state_after != trace.steps[0].state_before


def test_run_replay__when_strict_and_action_invalid__should_raise_replay_error():
    name = _probe_waiting_player()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": 999}),))

    with pytest.raises(ReplayError) as exc_info:
        run_replay(replay)
    assert exc_info.value.step_index == 0
    assert exc_info.value.event.player_name == name


def test_run_replay__when_non_strict_and_action_invalid__should_record_error_step():
    replay = _build_replay(actions=((_probe_waiting_player(), GameAction.DISCARD, {"tile_id": 999}),))

    trace = run_replay(replay, ReplayOptions(strict=False))
    assert len(trace.steps) == 1
    error_events = [e for e in trace.steps[0].emitted_events if e.event == EventType.ERROR]
    assert len(error_events) == 1


def test_run_replay__when_non_strict_and_service_raises_invalid_action__should_fail_the_replay():

    class RaisingService(_StubService):
        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            raise InvalidGameActionError(action="discard", seat=0, reason="test error")

    replay = _build_replay(actions=(("Alice", GameAction.DISCARD, {"tile_id": 0}),))
    with pytest.raises(InvalidGameActionError, match="test error"):
        run_replay(replay, ReplayOptions(strict=False), service_factory=RaisingService)


def test_run_replay__should_return_trace_with_seed():
    replay = _build_replay()
    trace = run_replay(replay)
    assert isinstance(trace, ReplayTrace)
    assert trace.seed == SEED


def test_run_replay__when_max_steps_zero__should_raise_step_limit_error():
    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))
    with pytest.raises(ReplayStepLimitError, match="exceeded 0 steps"):
        run_replay(replay, ReplayOptions(max_steps=0))


def test_run_replay__should_map_every_player_to_a_seat():
    replay = _build_replay()
    trace = run_replay(replay)
    assert len(trace.seat_by_player) == 4
    for name in PLAYER_NAMES:
        assert name in trace.seat_by_player
        assert trace.seat_by_player[name] in range(4)


def test_run_replay__when_strict_and_input_after_game_end__should_raise():

    class FinishedService(_StubService):
        def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> GameStart:
            start = super().start_game(game_id, player_names, seed=seed)
            state = start.runtime.state

            start.runtime.commit(
                state.model_copy(
                    update={"game_phase": GamePhase.FINISHED},
                )
            )
            return start

    replay = _build_replay(actions=(("Alice", GameAction.DISCARD, {"tile_id": 0}),))
    with pytest.raises(ReplayInputAfterGameEndError, match="Input remains after game end"):
        run_replay(replay, service_factory=FinishedService)


def test_run_replay__when_non_strict_and_input_after_game_end__should_skip_input():

    class FinishedService(_StubService):
        def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> GameStart:
            start = super().start_game(game_id, player_names, seed=seed)
            state = start.runtime.state

            start.runtime.commit(
                state.model_copy(
                    update={"game_phase": GamePhase.FINISHED},
                )
            )
            return start

    replay = _build_replay(actions=(("Alice", GameAction.DISCARD, {"tile_id": 0}),))
    trace = run_replay(replay, ReplayOptions(strict=False), service_factory=FinishedService)
    assert trace.final_state.game_phase == GamePhase.FINISHED
    assert len(trace.steps) == 0


def test_round_confirmation__when_round_advance_pending__should_inject_synthetic_confirm_steps():

    class RoundAdvanceService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._advance_pending = False
            self._advance_seats: list[int] = []

        def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> GameStart:
            start = super().start_game(game_id, player_names, seed=seed)
            self._advance_seats = list(start.seats)
            return start

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.CONFIRM_ROUND:
                if seat in self._advance_seats:
                    self._advance_seats.remove(seat)

                if not self._advance_seats:
                    self._advance_pending = False

                return _stub_update([])

            events = super().handle_action(runtime, seat=seat, action=action, data=data)
            self._advance_pending = True
            state = runtime.state

            self._advance_seats = [p.seat for p in state.round_state.players]
            return events

        def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
            return _round_advance_awaiting(self._advance_seats) if self._advance_pending else STUB_AWAITING

    name, tile = _probe_current_player_discard()
    replay = _build_replay(
        actions=(
            (name, GameAction.DISCARD, {"tile_id": tile}),
            (name, GameAction.DISCARD, {"tile_id": tile}),
        ),
    )

    trace = run_replay(replay, ReplayOptions(strict=False), service_factory=RoundAdvanceService)
    confirm_steps = [s for s in trace.steps if s.synthetic and s.input_event.action == GameAction.CONFIRM_ROUND]
    handled_steps = [s for s in trace.steps if s.input_event.action != GameAction.CONFIRM_ROUND]
    assert len(handled_steps) >= 2
    assert len(confirm_steps) == 4 * len(handled_steps)


def test_round_confirmation__when_strict_and_confirm_returns_error__should_raise_replay_error():

    class ConfirmErrorService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._advance_pending = False

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.CONFIRM_ROUND:
                return _stub_update(
                    [
                        ServiceEvent(
                            data=ErrorEvent(
                                code=GameErrorCode.INVALID_ACTION,
                                message="confirm_round error",
                                target=SeatTarget(seat=seat),
                            ),
                        ),
                    ]
                )

            events = super().handle_action(runtime, seat=seat, action=action, data=data)
            self._advance_pending = True
            return events

        def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
            return _round_advance_awaiting([0]) if self._advance_pending else STUB_AWAITING

    name, tile = _probe_current_player_discard()
    replay = _build_replay(
        actions=(
            (name, GameAction.DISCARD, {"tile_id": tile}),
            (name, GameAction.DISCARD, {"tile_id": tile}),
        ),
    )

    with pytest.raises(ReplayError, match="confirm_round error"):
        run_replay(replay, service_factory=ConfirmErrorService)


def test_step_limit__when_synthetic_confirms_reach_max_steps__should_raise_before_next_input():

    class RoundAdvanceService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._advance_pending = False

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.CONFIRM_ROUND:
                self._advance_pending = False
                return _stub_update([])

            events = super().handle_action(runtime, seat=seat, action=action, data=data)
            self._advance_pending = True
            return events

        def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
            return _round_advance_awaiting([0, 1]) if self._advance_pending else STUB_AWAITING

    name, tile = _probe_current_player_discard()
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
        run_replay(replay, ReplayOptions(max_steps=3, strict=False), service_factory=RoundAdvanceService)


def test_auto_confirm_rounds__when_input_has_confirm_round__should_raise_load_error():
    replay = _build_replay(actions=(("Alice", GameAction.CONFIRM_ROUND, {}),))

    with pytest.raises(ReplayLoadError, match=r"CONFIRM_ROUND.*auto_confirm_rounds=True"):
        run_replay(replay)


def test_auto_confirm_rounds__when_disabled_and_input_has_confirm_round__should_run_it_as_game_action():
    replay = _build_replay(actions=(("Alice", GameAction.CONFIRM_ROUND, {}),))

    # This should not raise ValueError; it may raise ReplayError due to
    # "no round pending confirmation" but that's a game-logic error, not validation.
    with pytest.raises(ReplayError):
        run_replay(replay, ReplayOptions(auto_confirm_rounds=False))


def test_auto_pass_calls__when_call_prompt_pending__should_inject_pass_for_other_seats():

    class CallPromptService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._inject_prompt = False

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.PASS:
                # Resolve the call prompt by removing it from state
                state = runtime.state

                prompt = state.round_state.pending_call_prompt
                if prompt is not None:
                    new_pending = prompt.pending_seats - {seat}
                    new_prompt = prompt.model_copy(update={"pending_seats": new_pending}) if new_pending else None
                    new_round = state.round_state.model_copy(
                        update={"pending_call_prompt": new_prompt},
                    )
                    runtime.commit(
                        state.model_copy(
                            update={"round_state": new_round},
                        )
                    )

                return _stub_update([])

            events = super().handle_action(runtime, seat=seat, action=action, data=data)
            # Inject a fake call prompt after a discard
            if action == GameAction.DISCARD:
                state = runtime.state
                other_seats = frozenset(p.seat for p in state.round_state.players if p.seat != seat)
                prompt = PendingCallPrompt(
                    kind=PromptKind.DISCARD,
                    tile_id=0,
                    from_seat=seat,
                    pending_seats=other_seats,
                    callers=tuple(_pon_caller(s) for s in sorted(other_seats)),
                )
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": prompt},
                )
                runtime.commit(
                    state.model_copy(
                        update={"round_state": new_round},
                    )
                )

            return events

    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    trace = run_replay(
        replay,
        ReplayOptions(strict=False),
        service_factory=CallPromptService,
    )
    synthetic_steps = [s for s in trace.steps if s.synthetic]
    assert len(synthetic_steps) == 3  # 3 other players auto-passed
    for step in synthetic_steps:
        assert step.input_event.action == GameAction.PASS


def test_auto_pass_calls__when_input_has_pass__should_raise_load_error():
    replay = _build_replay(actions=(("Alice", GameAction.PASS, {}),))

    with pytest.raises(ReplayLoadError, match=r"PASS.*auto_pass_calls=True"):
        run_replay(replay)


def test_auto_pass_calls__when_disabled_and_input_has_pass__should_run_it_as_game_action():
    replay = _build_replay(actions=(("Alice", GameAction.PASS, {}),))

    # This should not raise ValueError; it may raise ReplayError due to
    # "no call prompt pending" but that's a game-logic error, not validation.
    with pytest.raises(ReplayError):
        run_replay(
            replay,
            ReplayOptions(auto_pass_calls=False),
        )


def test_auto_pass_calls__when_player_responds_to_prompt__should_pass_only_the_others():
    # Discover actual seat assignments (seed-dependent)
    probe_state = MahjongGameService().start_game("probe-seats", list(PLAYER_NAMES), seed=SEED).runtime.state
    name_to_seat = {p.name: p.seat for p in probe_state.round_state.players}

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
            self._pass_calls: list[int] = []

        def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> GameStart:
            start = super().start_game(game_id, player_names, seed=seed)
            state = start.runtime.state

            prompt = PendingCallPrompt(
                kind=PromptKind.DISCARD,
                tile_id=0,
                from_seat=discarder_seat,
                pending_seats=frozenset({pon_seat, pass_seat}),
                callers=(_pon_caller(pon_seat), _pon_caller(pass_seat)),
            )
            new_round = state.round_state.model_copy(
                update={"pending_call_prompt": prompt},
            )
            start.runtime.commit(
                state.model_copy(
                    update={"round_state": new_round},
                )
            )
            return start

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.PASS:
                self._pass_calls.append(seat)
                state = runtime.state

                prompt = state.round_state.pending_call_prompt
                if prompt is not None:
                    new_pending = prompt.pending_seats - {seat}
                    new_prompt = prompt.model_copy(update={"pending_seats": new_pending}) if new_pending else None
                    new_round = state.round_state.model_copy(
                        update={"pending_call_prompt": new_prompt},
                    )
                    runtime.commit(
                        state.model_copy(
                            update={"round_state": new_round},
                        )
                    )

                return _stub_update([])

            if action == GameAction.CALL_PON:
                state = runtime.state

                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": None},
                )
                runtime.commit(
                    state.model_copy(
                        update={"round_state": new_round},
                    )
                )
                return _stub_update([])

            return super().handle_action(runtime, seat=seat, action=action, data=data)

    replay = _build_replay(actions=((pon_player, GameAction.CALL_PON, {"tile_id": 0}),))
    svc_instance = CallResponseService()

    trace = run_replay(
        replay,
        ReplayOptions(strict=False),
        service_factory=lambda: svc_instance,
    )
    # auto_passed_player should have been auto-passed, but NOT pon_player
    assert svc_instance._pass_calls == [pass_seat]
    synthetic_steps = [s for s in trace.steps if s.synthetic]
    assert len(synthetic_steps) == 1
    assert synthetic_steps[0].input_event.player_name == auto_passed_player
    assert synthetic_steps[0].input_event.action == GameAction.PASS


def test_auto_pass_calls__when_a_later_ron_follows_another_input__should_pass_its_seat_before_this_ron():
    dealer, dealer_tile = _probe_current_player_discard()
    probe_state = MahjongGameService().start_game("probe-seats", list(PLAYER_NAMES), seed=SEED).runtime.state
    seat_by_name = {p.name: p.seat for p in probe_state.round_state.players}
    ron_player, later_ron_player = [name for name in PLAYER_NAMES if name != dealer][:2]

    class RonPromptService(_StubService):
        def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> GameStart:
            start = super().start_game(game_id, player_names, seed=seed)
            ron_seats = (seat_by_name[ron_player], seat_by_name[later_ron_player])
            prompt = PendingCallPrompt(
                kind=PromptKind.DISCARD,
                tile_id=0,
                from_seat=seat_by_name[dealer],
                pending_seats=frozenset(ron_seats),
                callers=tuple(Caller(seat=seat, can_ron=True) for seat in sorted(ron_seats)),
            )
            state = start.runtime.state
            start.runtime.commit(
                state.model_copy(
                    update={"round_state": state.round_state.model_copy(update={"pending_call_prompt": prompt})}
                )
            )
            return start

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action not in (GameAction.PASS, GameAction.CALL_RON):
                return super().handle_action(runtime, seat=seat, action=action, data=data)

            state = runtime.state
            prompt = state.round_state.pending_call_prompt
            if prompt is not None:
                pending = prompt.pending_seats - {seat}
                new_prompt = prompt.model_copy(update={"pending_seats": pending}) if pending else None
                runtime.commit(
                    state.model_copy(
                        update={"round_state": state.round_state.model_copy(update={"pending_call_prompt": new_prompt})}
                    )
                )

            return _stub_update([])

    replay = _build_replay(
        actions=(
            (ron_player, GameAction.CALL_RON, {}),
            (dealer, GameAction.DISCARD, {"tile_id": dealer_tile}),
            (later_ron_player, GameAction.CALL_RON, {}),
        ),
    )

    trace = run_replay(replay, ReplayOptions(strict=False), service_factory=RonPromptService)
    assert [(s.input_event.player_name, s.input_event.action, s.synthetic) for s in trace.steps[:2]] == [
        (later_ron_player, GameAction.PASS, True),
        (ron_player, GameAction.CALL_RON, False),
    ]


def test_auto_pass_calls__when_strict_and_synthetic_pass_errors__should_raise_replay_error():

    class PassErrorService(_StubService):
        def __init__(self) -> None:
            super().__init__()

        def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> GameStart:
            start = super().start_game(game_id, player_names, seed=seed)
            state = start.runtime.state

            # Inject a fake call prompt
            prompt = PendingCallPrompt(
                kind=PromptKind.DISCARD,
                tile_id=0,
                from_seat=0,
                pending_seats=frozenset({1}),
                callers=(_pon_caller(1),),
            )
            new_round = state.round_state.model_copy(
                update={"pending_call_prompt": prompt},
            )
            start.runtime.commit(
                state.model_copy(
                    update={"round_state": new_round},
                )
            )
            return start

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.PASS:
                return _stub_update(
                    [
                        ServiceEvent(
                            data=ErrorEvent(
                                code=GameErrorCode.INVALID_PASS,
                                message="synthetic pass error",
                                target=BroadcastTarget(),
                            ),
                        ),
                    ]
                )

            return super().handle_action(runtime, seat=seat, action=action, data=data)

    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    with pytest.raises(ReplayError, match="synthetic pass error"):
        run_replay(
            replay,
            service_factory=PassErrorService,
        )


def test_auto_pass_calls__when_prompt_pending_after_last_input__should_pass_remaining_seats():

    class TrailingPromptService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_calls: list[int] = []

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.PASS:
                self._pass_calls.append(seat)
                state = runtime.state

                prompt = state.round_state.pending_call_prompt
                if prompt is not None:
                    new_pending = prompt.pending_seats - {seat}
                    new_prompt = prompt.model_copy(update={"pending_seats": new_pending}) if new_pending else None
                    new_round = state.round_state.model_copy(
                        update={"pending_call_prompt": new_prompt},
                    )
                    runtime.commit(
                        state.model_copy(
                            update={"round_state": new_round},
                        )
                    )

                return _stub_update([])

            events = super().handle_action(runtime, seat=seat, action=action, data=data)
            if action == GameAction.DISCARD:
                state = runtime.state
                other_seats = frozenset(p.seat for p in state.round_state.players if p.seat != seat)
                prompt = PendingCallPrompt(
                    kind=PromptKind.DISCARD,
                    tile_id=0,
                    from_seat=seat,
                    pending_seats=other_seats,
                    callers=tuple(_pon_caller(s) for s in sorted(other_seats)),
                )
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": prompt},
                )
                runtime.commit(
                    state.model_copy(
                        update={"round_state": new_round},
                    )
                )

            return events

    name, tile = _probe_current_player_discard()
    # Single discard is the only input; the trailing block handles the prompt
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    svc_instance = TrailingPromptService()
    trace = run_replay(
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


def test_run_replay__when_replay_has_rng_version__should_carry_it_to_trace():
    custom_version = "test-rng-v99"
    replay = _build_replay()
    replay = replay.model_copy(update={"rng_version": custom_version})

    trace = run_replay(replay)
    assert trace.rng_version == custom_version
    assert trace.rng_version != RNG_VERSION


def test_auto_pass_calls__when_strict_and_game_ends_during_pass__should_raise_input_after_game_end():

    class GameEndingPassService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_count = 0

        def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> GameStart:
            start = super().start_game(game_id, player_names, seed=seed)
            state = start.runtime.state

            # Inject a call prompt pending on seat 1
            prompt = PendingCallPrompt(
                kind=PromptKind.DISCARD,
                tile_id=0,
                from_seat=0,
                pending_seats=frozenset({1}),
                callers=(_pon_caller(1),),
            )
            new_round = state.round_state.model_copy(
                update={"pending_call_prompt": prompt},
            )
            start.runtime.commit(
                state.model_copy(
                    update={"round_state": new_round},
                )
            )
            return start

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.PASS:
                self._pass_count += 1
                state = runtime.state

                # Resolve prompt and end the game
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": None},
                )
                runtime.commit(
                    state.model_copy(
                        update={
                            "round_state": new_round,
                            "game_phase": GamePhase.FINISHED,
                        },
                    )
                )
                return _stub_update([])

            return super().handle_action(runtime, seat=seat, action=action, data=data)

    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    with pytest.raises(ReplayInputAfterGameEndError, match="Input remains after game end"):
        run_replay(
            replay,
            service_factory=GameEndingPassService,
        )


def test_auto_pass_calls__when_non_strict_and_game_ends_during_pass__should_skip_later_inputs():

    class GameEndingPassService(_StubService):
        def __init__(self) -> None:
            super().__init__()

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.PASS:
                state = runtime.state

                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": None},
                )
                runtime.commit(
                    state.model_copy(
                        update={
                            "round_state": new_round,
                            "game_phase": GamePhase.FINISHED,
                        },
                    )
                )
                return _stub_update([])

            events = super().handle_action(runtime, seat=seat, action=action, data=data)
            if action == GameAction.DISCARD:
                state = runtime.state
                other_seats = frozenset(p.seat for p in state.round_state.players if p.seat != seat)
                prompt = PendingCallPrompt(
                    kind=PromptKind.DISCARD,
                    tile_id=0,
                    from_seat=seat,
                    pending_seats=other_seats,
                    callers=tuple(_pon_caller(s) for s in sorted(other_seats)),
                )
                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": prompt},
                )
                runtime.commit(
                    state.model_copy(
                        update={"round_state": new_round},
                    )
                )

            return events

    name, tile = _probe_current_player_discard()
    # Two discards, but game ends during auto-pass after first discard
    replay = _build_replay(
        actions=(
            (name, GameAction.DISCARD, {"tile_id": tile}),
            (name, GameAction.DISCARD, {"tile_id": tile}),
        ),
    )

    trace = run_replay(
        replay,
        ReplayOptions(strict=False),
        service_factory=GameEndingPassService,
    )
    assert trace.final_state.game_phase == GamePhase.FINISHED
    # First discard processed, then auto-pass ends game, second discard skipped
    non_synthetic = [s for s in trace.steps if not s.synthetic]
    assert len(non_synthetic) == 1
    assert non_synthetic[0].input_event.action == GameAction.DISCARD


def test_auto_pass_calls__when_prompt_resolves_after_first_pass__should_stop_passing():

    class EarlyResolveService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_count = 0

        def start_game(
            self,
            game_id: str,
            player_names: list[str],
            *,
            seed: str | None = None,
            settings: GameSettings | None = None,
            wall: list[int] | None = None,
        ) -> GameStart:
            start = super().start_game(game_id, player_names, seed=seed)
            state = start.runtime.state

            prompt = PendingCallPrompt(
                kind=PromptKind.DISCARD,
                tile_id=0,
                from_seat=0,
                pending_seats=frozenset({1, 2}),
                callers=(_pon_caller(1), _pon_caller(2)),
            )
            new_round = state.round_state.model_copy(
                update={"pending_call_prompt": prompt},
            )
            start.runtime.commit(
                state.model_copy(
                    update={"round_state": new_round},
                )
            )
            return start

        def handle_action(
            self,
            runtime: GameRuntime,
            *,
            seat: int,
            action: GameAction,
            data: dict[str, Any],
        ) -> GameUpdate:
            if action == GameAction.PASS:
                self._pass_count += 1
                state = runtime.state

                new_round = state.round_state.model_copy(
                    update={"pending_call_prompt": None},
                )
                runtime.commit(
                    state.model_copy(
                        update={"round_state": new_round},
                    )
                )
                return _stub_update([])

            if action == GameAction.DISCARD:
                # Use real discard but ensure no new prompt is created
                events = super().handle_action(runtime, seat=seat, action=action, data=data)
                state = runtime.state

                if state.round_state.pending_call_prompt is not None:
                    new_round = state.round_state.model_copy(
                        update={"pending_call_prompt": None},
                    )
                    runtime.commit(
                        state.model_copy(
                            update={"round_state": new_round},
                        )
                    )

                return events

            return super().handle_action(runtime, seat=seat, action=action, data=data)

    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, GameAction.DISCARD, {"tile_id": tile}),))

    svc_instance = EarlyResolveService()
    trace = run_replay(
        replay,
        ReplayOptions(strict=False),
        service_factory=lambda: svc_instance,
    )
    # Only 1 PASS should have been sent (prompt resolved after first, breaking loop)
    assert svc_instance._pass_count == 1
    synthetic_pass_steps = [s for s in trace.steps if s.synthetic and s.input_event.action == GameAction.PASS]
    assert len(synthetic_pass_steps) == 1
