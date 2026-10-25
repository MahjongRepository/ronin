import asyncio
import threading
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from game.logic.enums import GameAction, GameErrorCode, TimeoutType, WaitKind
from game.logic.events import (
    EventType,
)
from game.logic.service import Awaiting
from game.messaging.types import SessionErrorCode
from game.session.manager import SessionManager
from game.session.models import GameLifecycle, GameSession, Participant, PlayerSpec
from game.session.timer import TimerConfig, TurnTimer
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import FakeGameRepository, MockConnection
from game.wire.events import EVENT_TYPE_INT
from shared.dal.models import GameEndReason
from shared.storage import LocalReplayStorage, replay_file_path

from .helpers import (
    arrange_exhaustive_draw,
    arrange_final_discard,
    arrange_ron_and_pon_on_a_discard,
    create_started_game,
    current_wait_id,
    fire_turn_timer_now,
    game_of,
    participant_of,
    run_timeout,
    runtime_of,
    wait_for_background_tasks,
)

if TYPE_CHECKING:
    from pathlib import Path


ARMING_CONFIG = TimerConfig(base_turn_seconds=5, initial_bank_seconds=20, meld_decision_seconds=3)


def _arm_double_ron_round_advance(manager: SessionManager, participant: Participant) -> None:
    participant.connection = MockConnection()
    participant.game.participants.append(participant)
    awaiting = Awaiting(
        kind=WaitKind.ROUND_ADVANCE,
        seats=frozenset({participant.seat}),
        wait_id=1,
        round_number=0,
        results_shown=2,
    )
    manager._start_wait_timers(participant.game, previous=awaiting, awaiting=awaiting)


class TestWaitTimerArming:
    @pytest.fixture
    def participant(self):
        game = GameSession(game_id="g1", timer_config=ARMING_CONFIG)
        return Participant(
            spec=PlayerSpec(name="Alice", user_id="user-0", game_ticket="ticket-0"),
            game=game,
            timer=TurnTimer(ARMING_CONFIG),
            seat=0,
        )

    @pytest.mark.parametrize(
        "arming",
        [
            (SessionManager._start_turn_timer, TimeoutType.TURN, 25.0),
            (SessionManager._start_meld_timer, TimeoutType.MELD, 3),
            (
                partial(SessionManager._start_round_advance_timer, results_shown=1),
                TimeoutType.ROUND_ADVANCE,
                ARMING_CONFIG.round_advance_timeout_seconds,
            ),
            (
                _arm_double_ron_round_advance,
                TimeoutType.ROUND_ADVANCE,
                2 * ARMING_CONFIG.round_advance_timeout_seconds,
            ),
        ],
    )
    async def test_wait_timer__when_an_armed_timer_expires__should_report_its_participant_and_timeout_type(
        self, participant, held_sleep, monkeypatch, arming
    ):
        manager = make_session_manager()
        timeout_log = []
        monkeypatch.setattr(manager, "_handle_timeout", lambda *timed_out: timeout_log.append(timed_out))
        start, timeout_type, duration = arming
        start(manager, participant)
        await asyncio.sleep(0)
        assert held_sleep.durations == [duration]

        await held_sleep.release_all()
        assert timeout_log == [(participant, timeout_type)]


class TestSessionManagerTimers:
    async def test_handle_timeout__when_turn_times_out__should_broadcast_resulting_events(self, manager):
        conns = create_started_game(manager)
        conns[0]._outbox.clear()

        run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=0)
        timeout_msgs = [m for m in conns[0].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(timeout_msgs) == 1


class TestWaitTimers:
    async def test_turn_timer__when_the_players_action_is_refused__should_keep_the_running_deadline(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice"])
        timer = participant_of(manager, conns[0]).timer
        deadline, bank = timer.task, timer._bank_seconds

        manager.handle_game_action(conns[0], action=GameAction.PASS, data={}, wait_id=current_wait_id(manager))
        assert [m["cd"] for m in conns[0].sent_messages] == [GameErrorCode.INVALID_PASS]
        assert timer.task is deadline
        assert not deadline.done()
        assert timer._bank_seconds == bank

        await manager.shutdown()

    async def test_meld_timers__when_one_of_two_callers_passes__should_keep_the_other_callers_deadline(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob", "Carol"])
        alice, bob, carol = (participant_of(manager, conn).seat for conn in conns)
        discarded_four_pin = arrange_ron_and_pon_on_a_discard(runtime_of(manager), discarder=alice, ron=bob, pon=carol)

        manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"tile_id": discarded_four_pin}, wait_id=current_wait_id(manager)
        )
        prompt = manager.get_game("game1").awaiting
        assert (prompt.kind, prompt.seats) == (WaitKind.CALL, frozenset({bob, carol}))
        carol_timer = participant_of(manager, conns[2]).timer
        carol_deadline = carol_timer.task

        manager.handle_game_action(conns[1], action=GameAction.PASS, data={}, wait_id=prompt.wait_id)
        assert manager.get_game("game1").awaiting == replace(prompt, seats=frozenset({carol}))
        assert participant_of(manager, conns[1]).timer.task is None
        assert carol_timer.task is carol_deadline
        assert not carol_deadline.done()

        await manager.shutdown()

    async def test_round_bonus__when_rounds_start_and_end__should_add_it_once_per_round_from_the_first(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice"])
        alice_seat = participant_of(manager, conns[0]).seat
        timer = participant_of(manager, conns[0]).timer
        config = TimerConfig()
        first_round_bank = config.initial_bank_seconds + config.round_bonus_seconds
        assert timer._bank_seconds == first_round_bank

        arrange_exhaustive_draw(runtime_of(manager))
        drawn_tile = runtime_of(manager).state.round_state.players[alice_seat].tiles[-1]
        manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"tile_id": drawn_tile}, wait_id=current_wait_id(manager)
        )
        assert manager.get_game("game1").awaiting.kind == WaitKind.ROUND_ADVANCE
        assert timer._bank_seconds == first_round_bank

        manager.handle_game_action(conns[0], action=GameAction.CONFIRM_ROUND, data={}, wait_id=current_wait_id(manager))
        second_round = manager.get_game("game1").awaiting
        assert (second_round.round_number, second_round.seats) == (1, frozenset({alice_seat}))
        assert timer._bank_seconds == first_round_bank + config.round_bonus_seconds

        if second_round.kind == WaitKind.CALL:
            manager.handle_game_action(conns[0], action=GameAction.PASS, data={}, wait_id=second_round.wait_id)
        else:
            drawn_tile = runtime_of(manager).state.round_state.players[alice_seat].tiles[-1]
            manager.handle_game_action(
                conns[0], action=GameAction.DISCARD, data={"tile_id": drawn_tile}, wait_id=second_round.wait_id
            )
        next_wait = manager.get_game("game1").awaiting
        assert next_wait.round_number == 1
        assert next_wait.wait_id != second_round.wait_id
        assert timer._bank_seconds == first_round_bank + config.round_bonus_seconds

        await manager.shutdown()

    async def test_round_bonus__when_a_round_starts_while_a_participant_is_away__should_skip_their_bank(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice, bob = (participant_of(manager, conn) for conn in conns)
        first_round_bank = TimerConfig().initial_bank_seconds + TimerConfig().round_bonus_seconds
        assert (alice.timer._bank_seconds, bob.timer._bank_seconds) == (first_round_bank, first_round_bank)
        manager.leave_game(conns[1], notify_player=False)
        game = game_of(manager)
        assert (game.awaiting.kind, game.awaiting.seats) == (WaitKind.TURN, frozenset({alice.seat}))

        arrange_exhaustive_draw(runtime_of(manager))
        drawn_tile = runtime_of(manager).state.round_state.players[alice.seat].tiles[-1]
        manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"tile_id": drawn_tile}, wait_id=current_wait_id(manager)
        )
        manager.handle_game_action(conns[0], action=GameAction.CONFIRM_ROUND, data={}, wait_id=current_wait_id(manager))
        assert game.awaiting.round_number == 1
        assert alice.timer._bank_seconds == first_round_bank + TimerConfig().round_bonus_seconds

        reconnecting = MockConnection()
        manager.register_connection(reconnecting)
        manager.reconnect(reconnecting, game_id="game1", session_token=bob.ticket)
        assert bob.connection is reconnecting
        assert bob.timer._bank_seconds == first_round_bank

        await manager.shutdown()


class _GatedReplayStorage(LocalReplayStorage):
    def __init__(self, replay_dir: Path) -> None:
        super().__init__(replay_dir)
        self.save_started = threading.Event()
        self.may_finish = threading.Event()

    def save_replay(self, game_id: str, content: str) -> None:
        self.save_started.set()
        self.may_finish.wait(timeout=5)
        super().save_replay(game_id, content)


def _discard_the_drawn_tile(manager: SessionManager, participant: Participant) -> None:
    drawn_tile = runtime_of(manager).state.round_state.players[participant.seat].tiles[-1]
    manager.handle_game_action(
        participant.connection,
        action=GameAction.DISCARD,
        data={"tile_id": drawn_tile},
        wait_id=current_wait_id(manager),
    )


def _disconnect(manager: SessionManager, participant: Participant) -> None:
    manager.leave_game(participant.connection, notify_player=False)


class TestTimerCallbackLifecycle:
    @pytest.mark.parametrize(
        ("player_names", "end_the_wait"),
        [(["Alice"], _discard_the_drawn_tile), (["Alice", "Bob"], _disconnect)],
        ids=["own_discard", "disconnect"],
    )
    async def test_turn_timeout__when_the_wait_ends_after_its_sleep_but_before_it_ran__should_drop_the_default_action(
        self, seeded_engine, held_sleep, player_names, end_the_wait
    ):
        manager = make_session_manager(seeded_engine)
        create_started_game(manager, player_names=player_names)
        game = game_of(manager)
        [awaited_seat] = game.awaiting.seats
        awaited = game.at_seat(awaited_seat)
        await asyncio.sleep(0)
        slept = awaited.timer.task
        assert len(held_sleep.durations) == 1

        held_sleep.wake_all()
        end_the_wait(manager, awaited)
        await asyncio.wait({slept})
        assert game.lifecycle is GameLifecycle.PLAYING
        assert len(runtime_of(manager).state.round_state.players[awaited_seat].discards) == 1
        successor = game.at_seat(min(game.awaiting.seats))
        assert successor.timer.task not in (None, slept)

        await manager.shutdown()

    async def test_turn_timeout__when_ai_turns_lead_back_to_the_human__should_keep_the_successor_timer_armed(
        self, seeded_engine
    ):
        manager = make_session_manager(seeded_engine)
        conns = create_started_game(manager, player_names=["Alice"])
        alice_seat = participant_of(manager, conns[0]).seat
        timer = participant_of(manager, conns[0]).timer
        timed_out = manager.get_game("game1").awaiting

        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await fired
        successor = manager.get_game("game1").awaiting
        assert (successor.kind, successor.seats) == (timed_out.kind, timed_out.seats)
        assert successor.wait_id != timed_out.wait_id
        draws_after_timeout = [m for m in conns[0].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(draws_after_timeout) == 1
        assert timer.task is not None
        assert timer.task is not fired
        assert not timer.task.done()

        await manager.shutdown()

    async def test_turn_timeout__when_callback_raises__should_fail_the_game_instead_of_stalling(
        self, seeded_engine, tmp_path
    ):
        game_repo = FakeGameRepository()
        manager = make_session_manager(seeded_engine, repository=game_repo, storage=LocalReplayStorage(tmp_path))
        conns = create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = participant_of(manager, conns[0]).seat
        seeded_engine.handle_timeout = MagicMock(side_effect=RuntimeError("engine fault"))

        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert game_repo.games["game1"].end_reason == GameEndReason.ERROR
        assert replay_file_path(tmp_path, "game1").exists()
        for conn in conns:
            assert [m["code"] for m in conn.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
            assert conn._close_code == 1011

    async def test_shutdown__when_a_game_end_is_suspended_in_its_replay_save__should_wait_for_it_and_leave_no_task(
        self, seeded_engine, tmp_path
    ):
        game_repo = FakeGameRepository()
        storage = _GatedReplayStorage(tmp_path)
        manager = make_session_manager(seeded_engine, repository=game_repo, storage=storage)
        conns = create_started_game(manager, player_names=["Alice"])
        alice_seat = participant_of(manager, conns[0]).seat
        arrange_final_discard(runtime_of(manager), seat=alice_seat)
        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        assert await asyncio.to_thread(storage.save_started.wait, 5)

        shutdown = asyncio.create_task(manager.shutdown())
        await asyncio.sleep(0)
        assert not shutdown.done()

        storage.may_finish.set()
        await shutdown
        assert fired.done()
        assert not fired.cancelled()
        assert game_repo.games["game1"].end_reason == GameEndReason.COMPLETED
        assert conns[0]._close_code == 1000
        assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()] == []
