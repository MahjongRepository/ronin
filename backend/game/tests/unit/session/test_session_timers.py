import asyncio
import threading
from dataclasses import replace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from game.logic.enums import GameAction, GameErrorCode, TimeoutType, WaitKind
from game.logic.events import (
    EventType,
)
from game.messaging.types import SessionErrorCode
from game.session.manager import SessionManager
from game.session.replay_collector import ReplayCollector
from game.session.timer import TimerConfig
from game.tests.mocks import MockGameRepository
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
    run_timeout,
    wait_for_background_tasks,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestSessionManagerTimers:
    async def test_session_timers__when_game_cleaned_up__should_remove_timers_and_lock(self, manager):
        conns = await create_started_game(manager)
        assert "game1" in manager._timer_manager._timers
        assert "game1" in manager._game_locks

        await manager.leave_game(conns[0])
        assert "game1" not in manager._timer_manager._timers
        assert "game1" not in manager._game_locks

    async def test_handle_timeout__when_turn_times_out__should_broadcast_resulting_events(self, manager):
        conns = await create_started_game(manager)
        conns[0]._outbox.clear()

        await run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=0)
        timeout_msgs = [m for m in conns[0].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(timeout_msgs) == 1

    async def test_handle_timeout__when_game_missing__should_not_raise(self, manager):
        # should not raise
        await run_timeout(manager, game_id="nonexistent", timeout_type=TimeoutType.TURN, seat=0)

    async def test_handle_timeout__when_game_removed_under_lock__should_broadcast_nothing(self, manager):
        conns = await create_started_game(manager)
        conns[0]._outbox.clear()

        # Remove the game but keep the lock to simulate concurrent cleanup
        manager._games.pop("game1", None)
        await run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=0)
        # no events broadcast
        assert len(conns[0].sent_messages) == 0

    async def test_handle_timeout__when_game_lock_missing__should_broadcast_nothing(self, manager):
        conns = await create_started_game(manager)

        # remove lock to simulate cleanup race
        manager._game_locks.pop("game1", None)
        conns[0]._outbox.clear()

        await run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=0)
        # no events broadcast
        assert len(conns[0].sent_messages) == 0


class TestPerPlayerTimers:
    async def test_per_player_timers__when_four_humans_start_game__should_create_timer_per_seat(self, manager):
        await create_started_game(manager, player_names=["P0", "P1", "P2", "P3"])
        for seat in range(4):
            timer = manager._timer_manager.get_timer("game1", seat)
            assert timer is not None


class TestWaitTimers:
    async def test_turn_timer__when_the_players_action_is_refused__should_keep_the_running_deadline(
        self, seeded_engine
    ):
        manager = SessionManager(seeded_engine)
        conns = await create_started_game(manager, player_names=["Alice"])
        alice_seat = manager._players[conns[0].connection_id].seat
        timer = manager._timer_manager.get_timer("game1", alice_seat)
        deadline, bank = timer.task, timer.bank_seconds

        await manager.handle_game_action(conns[0], action=GameAction.PASS, data={}, wait_id=current_wait_id(manager))
        assert [m["cd"] for m in conns[0].sent_messages] == [GameErrorCode.INVALID_PASS]
        assert timer.task is deadline
        assert not deadline.done()
        assert timer.bank_seconds == bank

        await manager.shutdown()

    async def test_meld_timers__when_one_of_two_callers_passes__should_keep_the_other_callers_deadline(
        self, seeded_engine
    ):
        manager = SessionManager(seeded_engine)
        conns = await create_started_game(manager, player_names=["Alice", "Bob", "Carol"])
        alice, bob, carol = (manager._players[conn.connection_id].seat for conn in conns)
        discarded_four_pin = arrange_ron_and_pon_on_a_discard(seeded_engine, discarder=alice, ron=bob, pon=carol)

        await manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"tile_id": discarded_four_pin}, wait_id=current_wait_id(manager)
        )
        prompt = manager.get_game("game1").awaiting
        assert (prompt.kind, prompt.seats) == (WaitKind.CALL, frozenset({bob, carol}))
        carol_timer = manager._timer_manager.get_timer("game1", carol)
        carol_deadline = carol_timer.task

        await manager.handle_game_action(conns[1], action=GameAction.PASS, data={}, wait_id=prompt.wait_id)
        assert manager.get_game("game1").awaiting == replace(prompt, seats=frozenset({carol}))
        assert manager._timer_manager.get_timer("game1", bob).task is None
        assert carol_timer.task is carol_deadline
        assert not carol_deadline.done()

        await manager.shutdown()

    async def test_round_bonus__when_rounds_start_and_end__should_add_it_once_per_round_from_the_first(
        self, seeded_engine
    ):
        manager = SessionManager(seeded_engine)
        conns = await create_started_game(manager, player_names=["Alice"])
        alice_seat = manager._players[conns[0].connection_id].seat
        timer = manager._timer_manager.get_timer("game1", alice_seat)
        config = TimerConfig()
        first_round_bank = config.initial_bank_seconds + config.round_bonus_seconds
        assert timer.bank_seconds == first_round_bank

        arrange_exhaustive_draw(seeded_engine, game_id="game1")
        drawn_tile = seeded_engine.get_game_state("game1").round_state.players[alice_seat].tiles[-1]
        await manager.handle_game_action(
            conns[0], action=GameAction.DISCARD, data={"tile_id": drawn_tile}, wait_id=current_wait_id(manager)
        )
        assert manager.get_game("game1").awaiting.kind == WaitKind.ROUND_ADVANCE
        assert timer.bank_seconds == first_round_bank

        await manager.handle_game_action(
            conns[0], action=GameAction.CONFIRM_ROUND, data={}, wait_id=current_wait_id(manager)
        )
        second_round = manager.get_game("game1").awaiting
        assert (second_round.kind, second_round.round_number) == (WaitKind.CALL, 1)
        assert timer.bank_seconds == first_round_bank + config.round_bonus_seconds

        await manager.handle_game_action(conns[0], action=GameAction.PASS, data={}, wait_id=second_round.wait_id)
        next_wait = manager.get_game("game1").awaiting
        assert next_wait.round_number == 1
        assert next_wait.wait_id != second_round.wait_id
        assert timer.bank_seconds == first_round_bank + config.round_bonus_seconds

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


async def _yield_until(condition) -> None:
    for _ in range(100):
        if condition():
            return

        await asyncio.sleep(0)

    raise AssertionError("condition never held")


class TestTimerCallbackLifecycle:
    async def test_turn_timeout__when_fired_while_the_players_own_discard_holds_the_lock__should_not_act_again(
        self, seeded_engine
    ):
        manager = SessionManager(seeded_engine)
        conns = await create_started_game(manager, player_names=["Alice"])
        alice_seat = manager._players[conns[0].connection_id].seat
        drawn_tile = seeded_engine.get_game_state("game1").round_state.players[alice_seat].tiles[-1]
        lock = manager._game_locks["game1"]
        await lock.acquire()

        discard = asyncio.create_task(
            manager.handle_game_action(
                conns[0], action=GameAction.DISCARD, data={"tile_id": drawn_tile}, wait_id=current_wait_id(manager)
            )
        )
        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await _yield_until(lambda: len(lock._waiters or ()) == 2)
        lock.release()
        await discard
        await fired
        assert len(seeded_engine.get_game_state("game1").round_state.players[alice_seat].discards) == 1
        assert manager._timer_manager.get_timer("game1", alice_seat).task is not None

        await manager.shutdown()

    async def test_turn_timeout__when_ai_turns_lead_back_to_the_human__should_keep_the_successor_timer_armed(
        self, seeded_engine
    ):
        manager = SessionManager(seeded_engine)
        conns = await create_started_game(manager, player_names=["Alice"])
        alice_seat = manager._players[conns[0].connection_id].seat
        timer = manager._timer_manager.get_timer("game1", alice_seat)
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
        game_repo = MockGameRepository()
        manager = SessionManager(
            seeded_engine,
            replay_collector=ReplayCollector(LocalReplayStorage(tmp_path)),
            game_repository=game_repo,
        )
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = manager._players[conns[0].connection_id].seat
        seeded_engine.handle_timeout = MagicMock(side_effect=RuntimeError("engine fault"))

        await fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await wait_for_background_tasks(manager)
        assert manager.get_game("game1") is None
        assert game_repo.games["game1"]["end_reason"] == GameEndReason.ERROR
        assert replay_file_path(tmp_path, "game1").exists()
        for conn in conns:
            assert [m["code"] for m in conn.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
            assert conn._close_code == 1011

    async def test_shutdown__when_timer_callback_suspended_in_game_end__should_wait_for_it_and_leave_no_task(
        self, seeded_engine, tmp_path
    ):
        game_repo = MockGameRepository()
        storage = _GatedReplayStorage(tmp_path)
        manager = SessionManager(seeded_engine, replay_collector=ReplayCollector(storage), game_repository=game_repo)
        conns = await create_started_game(manager, player_names=["Alice"])
        alice_seat = manager._players[conns[0].connection_id].seat
        arrange_final_discard(seeded_engine, game_id="game1", seat=alice_seat)
        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        assert await asyncio.to_thread(storage.save_started.wait, 5)

        shutdown = asyncio.create_task(manager.shutdown())
        await _yield_until(lambda: not manager._timer_manager._timers)
        assert not shutdown.done()

        storage.may_finish.set()
        await shutdown
        assert fired.done()
        assert not fired.cancelled()
        assert game_repo.games["game1"]["end_reason"] == GameEndReason.COMPLETED
        assert conns[0]._close_code == 1000
        assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()] == []
