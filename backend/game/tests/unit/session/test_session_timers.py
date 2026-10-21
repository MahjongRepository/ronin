import asyncio
import threading
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from game.logic.enums import CallType, GameAction, MeldViewType, TimeoutType
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DrawEvent,
    EventType,
    GameEndedEvent,
    MeldEvent,
    RoundEndEvent,
    RoundStartedEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.timer import TimerConfig, TurnTimer
from game.logic.types import (
    ExhaustiveDrawResult,
    PlayerStanding,
    TenpaiHand,
)
from game.messaging.types import SessionErrorCode
from game.session.manager import SessionManager
from game.session.models import Game, Player
from game.session.replay_collector import ReplayCollector
from game.tests.mocks import MockConnection, MockGameRepository, MockResultEvent
from game.wire.events import EVENT_TYPE_INT
from shared.dal.models import GameEndReason
from shared.storage import LocalReplayStorage, replay_file_path

from .helpers import (
    arrange_final_discard,
    create_started_game,
    fire_turn_timer_now,
    make_dummy_game_view,
    make_game_with_player,
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


class TestSessionManagerTimerIntegration:
    async def test_maybe_start_timer__when_draw_event__should_start_turn_timer(self, manager):
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        draw_event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                target="seat_0",
                seat=0,
                tile_id=42,
                available_actions=[],
            ),
            target=SeatTarget(seat=0),
        )
        await manager._maybe_start_timer(game, [draw_event])
        # timer should have an active task (turn timer started)
        assert timer._active_task is not None

        timer.cancel()

    async def test_maybe_start_timer__when_pon_meld_event__should_start_turn_timer(self, manager):
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        meld_event = ServiceEvent(
            event=EventType.MELD,
            data=MeldEvent(
                meld_type=MeldViewType.PON,
                caller_seat=0,
                from_seat=1,
                tile_ids=[0, 1, 2],
                called_tile_id=2,
            ),
            target=BroadcastTarget(),
        )
        await manager._maybe_start_timer(game, [meld_event])
        # timer should have an active task (turn timer started from pon meld)
        assert timer._active_task is not None

        timer.cancel()

    async def test_maybe_start_timer__when_call_prompt_event__should_start_meld_timer(self, manager):
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        call_event = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                type=EventType.CALL_PROMPT,
                target="all",
                call_type=CallType.MELD,
                tile_id=0,
                from_seat=1,
                callers=[0],
            ),
            target=SeatTarget(seat=0),
        )
        await manager._maybe_start_timer(game, [call_event])
        # timer should have an active task (meld timer started)
        assert timer._active_task is not None

        timer.cancel()

    async def test_maybe_start_timer__when_round_started_event__should_add_round_bonus_to_bank(self, manager):
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}
        initial_bank = timer._bank_seconds

        round_event = ServiceEvent(
            event=EventType.ROUND_STARTED,
            data=RoundStartedEvent(
                type=EventType.ROUND_STARTED,
                target="seat_0",
                **make_dummy_game_view().model_dump(),
            ),
            target=SeatTarget(seat=0),
        )
        await manager._maybe_start_timer(game, [round_event])
        config = TimerConfig()
        assert timer._bank_seconds == initial_bank + config.round_bonus_seconds

    async def test_maybe_start_timer__when_round_end_event__should_start_fixed_round_advance_timer(self, manager):
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}
        manager._game_locks["game1"] = asyncio.Lock()

        round_end_event = ServiceEvent(
            event=EventType.ROUND_END,
            data=RoundEndEvent(
                type=EventType.ROUND_END,
                target="all",
                result=ExhaustiveDrawResult(
                    tempai_seats=[0],
                    noten_seats=[1, 2, 3],
                    tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
                    scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
                    score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
                ),
            ),
            target=BroadcastTarget(),
        )
        await manager._maybe_start_timer(game, [round_end_event])
        # timer should have an active task (round advance timer started)
        assert timer._active_task is not None
        # fixed timer doesn't consume bank time
        assert timer._turn_start_time is None

        timer.cancel()

    async def test_maybe_start_timer__when_game_end_event__should_not_start_timer(self, manager):
        game, _player, _conn = make_game_with_player(manager)
        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer}

        game_end_event = ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                winner_seat=0,
                standings=[
                    PlayerStanding(seat=0, score=25000, final_score=0),
                ],
            ),
            target=BroadcastTarget(),
        )
        await manager._maybe_start_timer(game, [game_end_event])
        # timer task should not be started (game ended)
        assert timer._active_task is None

    async def test_maybe_start_timer__when_game_has_no_timers__should_not_raise(self, manager):
        game, _player, _conn = make_game_with_player(manager)
        # do not set up a timer for the game

        generic_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="Alice",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        # should return without error
        await manager._maybe_start_timer(game, [generic_event])

    async def test_maybe_start_timer__when_no_player_at_event_seat__should_not_start_timer(self, manager):
        game = Game(game_id="game1")
        conn = MockConnection()
        # player at seat 1, but draw event targets seat 0 (no player there)
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="game1", seat=1)
        game.players[conn.connection_id] = player
        manager._games["game1"] = game

        timer = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer, 1: TurnTimer()}

        draw_event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                target="seat_0",
                seat=0,
                tile_id=42,
                available_actions=[],
            ),
            target=SeatTarget(seat=0),
        )
        await manager._maybe_start_timer(game, [draw_event])
        assert timer._active_task is None


class TestPerPlayerTimers:
    def _make_pvp_game_with_two_players(
        self,
        manager,
    ) -> tuple[Game, Player, Player, MockConnection, MockConnection]:
        conn1 = MockConnection()
        conn2 = MockConnection()
        game = Game(game_id="game1")
        player1 = Player(connection=conn1, name="Alice", session_token="tok-alice", game_id="game1", seat=0)
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="game1", seat=1)
        game.players[conn1.connection_id] = player1
        game.players[conn2.connection_id] = player2

        manager._games["game1"] = game
        manager._players[conn1.connection_id] = player1
        manager._players[conn2.connection_id] = player2
        manager._connections[conn1.connection_id] = conn1
        manager._connections[conn2.connection_id] = conn2
        return game, player1, player2, conn1, conn2

    async def test_per_player_timers__when_four_humans_start_game__should_create_timer_per_seat(self, manager):
        await create_started_game(manager, num_ai_players=0, player_names=["P0", "P1", "P2", "P3"])
        for seat in range(4):
            timer = manager._timer_manager.get_timer("game1", seat)
            assert timer is not None

    async def test_per_player_timers__when_round_started__should_add_round_bonus_to_every_timer(self, manager):
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_players(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        initial_bank_0 = timer0._bank_seconds
        initial_bank_1 = timer1._bank_seconds

        round_event = ServiceEvent(
            event=EventType.ROUND_STARTED,
            data=RoundStartedEvent(
                type=EventType.ROUND_STARTED,
                target="seat_0",
                **make_dummy_game_view().model_dump(),
            ),
            target=SeatTarget(seat=0),
        )
        await manager._maybe_start_timer(game, [round_event])
        config = TimerConfig()
        assert timer0._bank_seconds == initial_bank_0 + config.round_bonus_seconds
        assert timer1._bank_seconds == initial_bank_1 + config.round_bonus_seconds

    async def test_per_player_timers__when_call_prompts_for_two_seats__should_start_meld_timer_for_each(self, manager):
        game, _p1, _p2, _c1, _c2 = self._make_pvp_game_with_two_players(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        call_events = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[0],
                ),
                target=SeatTarget(seat=0),
            ),
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[1],
                ),
                target=SeatTarget(seat=1),
            ),
        ]
        await manager._maybe_start_timer(game, call_events)
        # both timers should have active tasks (meld timer started for each)
        assert timer0._active_task is not None
        assert timer1._active_task is not None

        timer0.cancel()
        timer1.cancel()

    async def test_per_player_timers__when_one_caller_acts__should_cancel_sibling_meld_timer(self, manager):
        game, _p1, _p2, conn1, _c2 = self._make_pvp_game_with_two_players(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        call_events = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[0],
                ),
                target=SeatTarget(seat=0),
            ),
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[1],
                ),
                target=SeatTarget(seat=1),
            ),
        ]
        await manager._maybe_start_timer(game, call_events)
        assert timer0._active_task is not None
        assert timer1._active_task is not None

        # player at seat 0 acts (handle_game_action)
        conn1._outbox.clear()
        await manager.handle_game_action(conn1, action=GameAction.DISCARD, data={})
        # seat 0's timer should be stopped (bank time deducted), seat 1's cancelled
        assert timer1._active_task is None

    async def test_per_player_timers__when_one_caller_passes_and_others_pending__should_stop_only_their_timer(
        self, manager
    ):
        game, _p1, _p2, conn1, _c2 = self._make_pvp_game_with_two_players(manager)
        timer0 = TurnTimer()
        timer1 = TurnTimer()
        manager._timer_manager._timers["game1"] = {0: timer0, 1: timer1}
        manager._game_locks["game1"] = asyncio.Lock()

        call_events = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[0],
                ),
                target=SeatTarget(seat=0),
            ),
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    target="all",
                    call_type=CallType.MELD,
                    tile_id=42,
                    from_seat=2,
                    callers=[1],
                ),
                target=SeatTarget(seat=1),
            ),
        ]
        await manager._maybe_start_timer(game, call_events)
        assert timer0._active_task is not None
        assert timer1._active_task is not None

        # mock returns empty events (partial pass, other callers still pending)
        manager._game_service.handle_action = AsyncMock(return_value=[])
        conn1._outbox.clear()
        await manager.handle_game_action(conn1, action=GameAction.PASS, data={})
        # seat 0's timer should be stopped, seat 1's timer should still be running
        assert timer0._active_task is None
        assert timer1._active_task is not None

        timer1.cancel()


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
            manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={"tile_id": drawn_tile})
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

        fired = fire_turn_timer_now(manager, game_id="game1", seat=alice_seat)
        await fired
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
        conns = await create_started_game(manager, num_ai_players=2, player_names=["Alice", "Bob"])
        alice_seat = manager._players[conns[0].connection_id].seat
        seeded_engine.handle_timeout = AsyncMock(side_effect=RuntimeError("engine fault"))

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
