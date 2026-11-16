from typing import TYPE_CHECKING

import pytest

from game.engine import (
    RNG_VERSION,
    Awaiting,
    Call,
    Discard,
    EventType,
    GameEvent,
    GameOver,
    Kan,
    KanType,
    MahjongGameService,
    Pass,
    Pon,
    Refusal,
    RefusalCode,
    RefusalKind,
    Ron,
)
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
from game.tests.helpers.builders import start_game_in_play
from game.tests.helpers.hands import (
    PIN_3_TRIPLE_RON_CALLER_HANDS,
    PIN_3_TRIPLE_RON_DEALER_HAND,
    PIN_3_TRIPLE_RON_DISCARD,
)
from game.tests.helpers.start_wall import make_start_wall

if TYPE_CHECKING:
    from collections.abc import Sequence

    from game.engine import Action, GameRuntime, StartPosition

PLAYER_NAMES = ("Alice", "Bob", "Charlie", "Diana")
SEED = "a" * 192


def _build_replay(
    seed: str = SEED,
    player_names: tuple[str, str, str, str] = PLAYER_NAMES,
    actions: tuple[tuple[str, Action], ...] = (),
) -> ReplayInput:
    events = tuple(ReplayInputEvent(player_name=name, action=action) for name, action in actions)
    return ReplayInput(seed=seed, player_names=player_names, events=events)


class _StubService:
    def __init__(self) -> None:
        self._inner = MahjongGameService()
        self.awaiting: Awaiting | None = None

    def open_call(self, seats: frozenset[int]) -> None:
        self.awaiting = Call(seats=seats)

    def answer_call(self, seat: int) -> None:
        if isinstance(self.awaiting, Call):
            remaining = self.awaiting.seats - {seat}
            self.awaiting = Call(seats=remaining) if remaining else None

    def new_game(
        self,
        seed: str,
        *,
        walls: Sequence[Sequence[int]] = (),
        start: StartPosition | None = None,
    ) -> tuple[GameRuntime, list[GameEvent]]:
        return self._inner.new_game(seed, walls=walls, start=start)

    def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
        return self._inner.act(runtime, seat, action)

    def begin_round(self, runtime: GameRuntime) -> list[GameEvent] | Refusal:
        return self._inner.begin_round(runtime)

    def deal_next_round(self, runtime: GameRuntime) -> list[GameEvent] | Refusal:
        return self._inner.deal_next_round(runtime)

    def get_awaiting(self, runtime: GameRuntime) -> Awaiting:
        return self.awaiting if self.awaiting is not None else self._inner.get_awaiting(runtime)


def _pin_3_ron_replay() -> ReplayInput:
    dealer, ron_caller, _, _ = PLAYER_NAMES
    return ReplayInput(
        seed=SEED,
        player_names=PLAYER_NAMES,
        walls=(
            make_start_wall(
                (PIN_3_TRIPLE_RON_DEALER_HAND, *PIN_3_TRIPLE_RON_CALLER_HANDS),
                draws=(PIN_3_TRIPLE_RON_DISCARD,),
            ),
        ),
        events=(
            ReplayInputEvent(player_name=dealer, action=Discard(tile=PIN_3_TRIPLE_RON_DISCARD)),
            ReplayInputEvent(player_name=ron_caller, action=Ron()),
        ),
    )


def _probe_current_player_discard() -> tuple[str, int]:
    state = start_game_in_play(MahjongGameService(), seed=SEED).runtime.state
    seat = state.round_state.current_player_seat
    return PLAYER_NAMES[seat], state.round_state.players[seat].tiles[-1]


def _probe_foreign_tile(name: str) -> int:
    state = start_game_in_play(MahjongGameService(), seed=SEED).runtime.state
    held = set(state.round_state.players[PLAYER_NAMES.index(name)].tiles)
    return next(tile for tile in range(136) if tile not in held)


def _probe_waiting_player() -> str:
    state = start_game_in_play(MahjongGameService(), seed=SEED).runtime.state
    seat = (state.round_state.current_player_seat + 1) % 4
    return PLAYER_NAMES[seat]


def test_run_replay__when_discard_input__should_trace_discard_step():
    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, Discard(tile=tile)),))

    trace = run_replay(replay)
    assert isinstance(trace, ReplayTrace)
    assert trace.seed == SEED
    assert len(trace.steps) >= 1
    assert trace.steps[0].input_event.player_name == name
    assert trace.steps[0].state_before is not None
    assert trace.steps[0].state_after is not None
    assert isinstance(trace.steps[0].input_event.action, Discard)
    assert any(e.type == EventType.DISCARD for e in trace.steps[0].emitted_events)
    assert trace.steps[0].state_after != trace.steps[0].state_before


def test_run_replay__when_strict_and_action_invalid__should_raise_replay_error():
    name = _probe_waiting_player()
    replay = _build_replay(actions=((name, Discard(tile=0)),))

    with pytest.raises(ReplayError) as exc_info:
        run_replay(replay)
    assert exc_info.value.step_index == 0
    assert exc_info.value.event.player_name == name


def test_run_replay__when_non_strict_and_action_invalid__should_record_the_refused_step():
    replay = _build_replay(actions=((_probe_waiting_player(), Discard(tile=0)),))

    trace = run_replay(replay, ReplayOptions(strict=False))
    assert len(trace.steps) == 1
    assert trace.steps[0].emitted_events == ()
    assert trace.steps[0].refusal == Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.SEAT_NOT_AWAITED)
    assert trace.steps[0].state_after is trace.steps[0].state_before


def test_run_replay__when_non_strict_and_the_action_is_not_offered__should_fail_the_replay():
    name, _tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, Discard(tile=_probe_foreign_tile(name))),))

    with pytest.raises(ReplayError, match="refused not_offered: tile_not_held"):
        run_replay(replay, ReplayOptions(strict=False))


def test_run_replay__should_return_trace_with_seed():
    replay = _build_replay()
    trace = run_replay(replay)
    assert isinstance(trace, ReplayTrace)
    assert trace.seed == SEED


def test_run_replay__when_max_steps_zero__should_raise_step_limit_error():
    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, Discard(tile=tile)),))
    with pytest.raises(ReplayStepLimitError, match="exceeded 0 steps"):
        run_replay(replay, ReplayOptions(max_steps=0))


def test_run_replay__should_seat_each_player_at_its_index():
    trace = run_replay(_build_replay())
    assert trace.seat_by_player == {"Alice": 0, "Bob": 1, "Charlie": 2, "Diana": 3}


def test_run_replay__when_strict_and_input_after_game_end__should_raise():

    class FinishedService(_StubService):
        def begin_round(self, runtime: GameRuntime) -> list[GameEvent] | Refusal:
            update = super().begin_round(runtime)
            self.awaiting = GameOver()
            return update

    replay = _build_replay(actions=(("Alice", Discard(tile=0)),))
    with pytest.raises(ReplayInputAfterGameEndError, match="Input remains after game end"):
        run_replay(replay, service_factory=FinishedService)


def test_run_replay__when_non_strict_and_input_after_game_end__should_skip_input():

    class FinishedService(_StubService):
        def begin_round(self, runtime: GameRuntime) -> list[GameEvent] | Refusal:
            update = super().begin_round(runtime)
            self.awaiting = GameOver()
            return update

    replay = _build_replay(actions=(("Alice", Discard(tile=0)),))
    trace = run_replay(replay, ReplayOptions(strict=False), service_factory=FinishedService)
    assert len(trace.steps) == 0


def test_round_advance__when_the_round_ends__should_deal_and_begin_the_next_round_in_one_synthetic_step():
    trace = run_replay(_pin_3_ron_replay())

    *_, ron_step, advance = trace.steps
    assert ron_step.input_event is not None
    assert ron_step.input_event.action == Ron()
    assert (advance.input_event, advance.synthetic) == (None, True)
    assert [e.type for e in advance.emitted_events][:5] == [EventType.ROUND_STARTED] * 4 + [EventType.DRAW]
    assert advance.state_before is ron_step.state_after
    assert (advance.state_after.round_number, advance.state_after.round_state.result) == (1, None)


def test_step_limit__when_a_round_advance_reaches_max_steps__should_raise():
    with pytest.raises(ReplayStepLimitError, match="exceeded 4 steps"):
        run_replay(_pin_3_ron_replay(), ReplayOptions(max_steps=4))


def test_step_limit__when_synthetic_passes_reach_max_steps__should_raise_before_the_ron_input():
    dealer, ron_caller, first_passer, second_passer = PLAYER_NAMES
    replay = _pin_3_ron_replay()

    with pytest.raises(ReplayStepLimitError, match="exceeded 3 steps"):
        run_replay(replay, ReplayOptions(advance_rounds=False, max_steps=3))

    trace = run_replay(replay, ReplayOptions(advance_rounds=False, max_steps=4))
    assert [(s.input_event.player_name, s.input_event.action) for s in trace.steps] == [
        (dealer, Discard(tile=PIN_3_TRIPLE_RON_DISCARD)),
        (first_passer, Pass()),
        (second_passer, Pass()),
        (ron_caller, Ron()),
    ]


def test_auto_pass_calls__when_call_prompt_pending__should_inject_pass_for_other_seats():

    class CallPromptService(_StubService):
        def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
            if action == Pass():
                self.answer_call(seat)
                return []

            events = super().act(runtime, seat, action)
            if isinstance(action, Discard):
                self.open_call(frozenset(other for other in range(4) if other != seat))

            return events

    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, Discard(tile=tile)),))

    trace = run_replay(
        replay,
        ReplayOptions(strict=False),
        service_factory=CallPromptService,
    )
    synthetic_steps = [s for s in trace.steps if s.synthetic]
    assert len(synthetic_steps) == 3  # 3 other players auto-passed
    for step in synthetic_steps:
        assert step.input_event.action == Pass()


def test_auto_pass_calls__when_input_has_pass__should_raise_load_error():
    replay = _build_replay(actions=(("Alice", Pass()),))

    with pytest.raises(ReplayLoadError, match=r"PASS.*auto_pass_calls=True"):
        run_replay(replay)


def test_auto_pass_calls__when_disabled_and_input_has_pass__should_run_it_as_game_action():
    replay = _build_replay(actions=(("Alice", Pass()),))

    # This should not raise ValueError; it may raise ReplayError due to
    # "no call prompt pending" but that's a game-logic error, not validation.
    with pytest.raises(ReplayError):
        run_replay(
            replay,
            ReplayOptions(auto_pass_calls=False),
        )


def test_auto_pass_calls__when_player_responds_to_prompt__should_pass_only_the_others():
    name_to_seat = {name: seat for seat, name in enumerate(PLAYER_NAMES)}

    # Pick two seats: pon_player calls PON, auto_passed_player should be auto-passed
    pon_player = "Bob"
    auto_passed_player = "Charlie"
    pon_seat = name_to_seat[pon_player]
    pass_seat = name_to_seat[auto_passed_player]

    class CallResponseService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_calls: list[int] = []
            self.open_call(frozenset({pon_seat, pass_seat}))

        def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
            if action == Pass():
                self._pass_calls.append(seat)
                self.answer_call(seat)
                return []

            if action == Pon():
                self.awaiting = None
                return []

            return super().act(runtime, seat, action)

    replay = _build_replay(actions=((pon_player, Pon()),))
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
    assert synthetic_steps[0].input_event.action == Pass()


def test_auto_pass_calls__when_a_later_ron_follows_another_input__should_pass_its_seat_before_this_ron():
    dealer, dealer_tile = _probe_current_player_discard()
    seat_by_name = {name: seat for seat, name in enumerate(PLAYER_NAMES)}
    ron_player, later_ron_player = [name for name in PLAYER_NAMES if name != dealer][:2]

    class RonPromptService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self.open_call(frozenset({seat_by_name[ron_player], seat_by_name[later_ron_player]}))

        def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
            if action not in (Pass(), Ron()):
                return super().act(runtime, seat, action)

            self.answer_call(seat)
            return []

    replay = _build_replay(
        actions=(
            (ron_player, Ron()),
            (dealer, Discard(tile=dealer_tile)),
            (later_ron_player, Ron()),
        ),
    )

    trace = run_replay(replay, ReplayOptions(strict=False), service_factory=RonPromptService)
    assert [(s.input_event.player_name, s.input_event.action, s.synthetic) for s in trace.steps[:2]] == [
        (later_ron_player, Pass(), True),
        (ron_player, Ron(), False),
    ]


@pytest.mark.parametrize("kan_type", [KanType.CLOSED, KanType.ADDED])
def test_auto_pass_calls__when_prompted_seat_declares_self_kan__should_pass_its_prompt_first(kan_type: KanType):
    seat_by_name = {name: seat for seat, name in enumerate(PLAYER_NAMES)}
    kan_player = "Bob"

    class CallPromptService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self.open_call(frozenset({seat_by_name[kan_player]}))

        def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
            if action == Pass():
                self.answer_call(seat)

            return []

    replay = _build_replay(actions=((kan_player, Kan(kan_type=kan_type, tile=0)),))

    trace = run_replay(replay, ReplayOptions(strict=False), service_factory=CallPromptService)
    assert [(s.input_event.player_name, s.input_event.action, s.synthetic) for s in trace.steps] == [
        (kan_player, Pass(), True),
        (kan_player, Kan(kan_type=kan_type, tile=0), False),
    ]


def test_auto_pass_calls__when_strict_and_synthetic_pass_errors__should_raise_replay_error():

    class PassErrorService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self.open_call(frozenset({1}))

        def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
            if action == Pass():
                return Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.ALREADY_ANSWERED)

            return super().act(runtime, seat, action)

    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, Discard(tile=tile)),))

    with pytest.raises(ReplayError, match="refused not_awaited: already_answered"):
        run_replay(
            replay,
            service_factory=PassErrorService,
        )


def test_auto_pass_calls__when_prompt_pending_after_last_input__should_pass_remaining_seats():

    class TrailingPromptService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_calls: list[int] = []

        def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
            if action == Pass():
                self._pass_calls.append(seat)
                self.answer_call(seat)
                return []

            events = super().act(runtime, seat, action)
            if isinstance(action, Discard):
                self.open_call(frozenset(other for other in range(4) if other != seat))

            return events

    name, tile = _probe_current_player_discard()
    # Single discard is the only input; the trailing block handles the prompt
    replay = _build_replay(actions=((name, Discard(tile=tile)),))

    svc_instance = TrailingPromptService()
    trace = run_replay(
        replay,
        ReplayOptions(strict=False, advance_rounds=False),
        service_factory=lambda: svc_instance,
    )
    # The in-loop auto-pass does NOT fire (no subsequent input event to trigger it).
    # The trailing block after the loop injects PASS for all 3 other seats.
    synthetic_steps = [s for s in trace.steps if s.synthetic]
    assert len(synthetic_steps) == 3
    for step in synthetic_steps:
        assert step.input_event.action == Pass()
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
            self.open_call(frozenset({1}))

        def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
            if action == Pass():
                self.awaiting = GameOver()
                return []

            return super().act(runtime, seat, action)

    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, Discard(tile=tile)),))

    with pytest.raises(ReplayInputAfterGameEndError, match="Input remains after game end"):
        run_replay(
            replay,
            service_factory=GameEndingPassService,
        )


def test_auto_pass_calls__when_non_strict_and_game_ends_during_pass__should_skip_later_inputs():

    class GameEndingPassService(_StubService):
        def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
            if action == Pass():
                self.awaiting = GameOver()
                return []

            events = super().act(runtime, seat, action)
            if isinstance(action, Discard):
                self.open_call(frozenset(other for other in range(4) if other != seat))

            return events

    name, tile = _probe_current_player_discard()
    # Two discards, but game ends during auto-pass after first discard
    replay = _build_replay(
        actions=(
            (name, Discard(tile=tile)),
            (name, Discard(tile=tile)),
        ),
    )

    trace = run_replay(
        replay,
        ReplayOptions(strict=False),
        service_factory=GameEndingPassService,
    )
    # First discard processed, then auto-pass ends game, second discard skipped
    non_synthetic = [s for s in trace.steps if not s.synthetic]
    assert len(non_synthetic) == 1
    assert isinstance(non_synthetic[0].input_event.action, Discard)


def test_auto_pass_calls__when_prompt_resolves_after_first_pass__should_stop_passing():

    class EarlyResolveService(_StubService):
        def __init__(self) -> None:
            super().__init__()
            self._pass_count = 0
            self.open_call(frozenset({1, 2}))

        def act(self, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent] | Refusal:
            if action == Pass():
                self._pass_count += 1
                self.awaiting = None
                return []

            return super().act(runtime, seat, action)

    name, tile = _probe_current_player_discard()
    replay = _build_replay(actions=((name, Discard(tile=tile)),))

    svc_instance = EarlyResolveService()
    trace = run_replay(
        replay,
        ReplayOptions(strict=False),
        service_factory=lambda: svc_instance,
    )
    # Only 1 PASS should have been sent (prompt resolved after first, breaking loop)
    assert svc_instance._pass_count == 1
    synthetic_pass_steps = [s for s in trace.steps if s.synthetic and s.input_event.action == Pass()]
    assert len(synthetic_pass_steps) == 1
