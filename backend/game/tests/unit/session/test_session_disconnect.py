import asyncio
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, ServiceEvent
from game.messaging.types import SessionMessageType
from game.session.manager import SessionManager
from game.tests.mocks import MockConnection, MockResultEvent, mock_update
from game.wire.events import EVENT_TYPE_INT

from .helpers import create_started_game, current_wait_id, run_timeout

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import pytest


class TestSessionManagerDisconnect:
    async def test_disconnect__when_one_of_two_humans_leaves__should_replace_with_ai_and_keep_game(self, seeded_engine):
        manager = SessionManager(seeded_engine)
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        alice_seat = manager._players[conns[0].connection_id].seat
        bob_seat = manager._players[conns[1].connection_id].seat

        await manager.leave_game(conns[0])
        assert manager.get_game("game1") is not None
        snapshot = seeded_engine.build_reconnection_snapshot("game1", bob_seat)
        assert snapshot.players[alice_seat].is_ai_player is True
        assert snapshot.players[bob_seat].is_ai_player is False

    async def test_disconnect__when_last_human_leaves__should_not_replace_with_ai_and_clean_up_game(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        game = manager.get_game("game1")
        assert game.started is True

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, seat):
            replace_calls.append((game_id, seat))
            return original_replace(game_id, seat)

        manager._game_service.replace_with_ai_player = tracking_replace

        # first player leaves (triggers AI player replacement)
        await manager.leave_game(conns[0])
        assert len(replace_calls) == 1

        # second player leaves (last player -- no AI player replacement, game cleaned up)
        await manager.leave_game(conns[1])
        assert len(replace_calls) == 1  # no additional call
        assert manager.get_game("game1") is None

    async def test_disconnect__when_player_leaves__should_remove_only_their_timer(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        # verify timers exist for both seats
        assert manager._timer_manager.get_timer("game1", 0) is not None
        assert manager._timer_manager.get_timer("game1", 1) is not None

        await manager.leave_game(conns[0])
        # seat 0's timer should be removed
        assert manager._timer_manager.get_timer("game1", 0) is None
        # seat 1's timer should remain
        assert manager._timer_manager.get_timer("game1", 1) is not None

    async def test_disconnect__when_ai_replacement_produces_events__should_broadcast_them(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        # make process_ai_player_actions_after_replacement return an event
        ai_player_event = ServiceEvent(
            data=MockResultEvent(
                type=EventType.DRAW,
                target=BroadcastTarget(),
                seat=0,
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
        )
        manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            return_value=mock_update([ai_player_event]),
        )

        await manager.leave_game(conns[0])
        # Bob should receive the AI player action event
        ai_player_msgs = [m for m in conns[1].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(ai_player_msgs) == 1

    async def test_disconnect__when_stale_timeout_fires_for_replaced_seat__should_send_nothing(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        # Alice disconnects
        await manager.leave_game(conns[0])
        conns[1]._outbox.clear()

        # stale timeout fires for Alice's old seat (seat 0)
        # should be a no-op because _get_player_at_seat returns None for seat 0
        await run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=0)
        assert len(conns[1].sent_messages) == 0

    async def test_disconnect__when_game_lock_missing__should_skip_ai_replacement_and_mark_session_disconnected(
        self, manager
    ):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        player = manager._players.get(conns[0].connection_id)
        token = player.session_token
        # remove the game lock to simulate the startup window where
        # game.started is True but the lock hasn't been created yet
        manager._game_locks.pop("game1", None)

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, seat):
            replace_calls.append((game_id, seat))
            return original_replace(game_id, seat)

        manager._game_service.replace_with_ai_player = tracking_replace

        # leave_game should skip AI player replacement (no lock) but use started-game
        # session semantics (mark_disconnected, not remove_session)
        await manager.leave_game(conns[0])
        assert len(replace_calls) == 0
        # session should be marked disconnected (not removed) since game.started is True
        session = manager._session_store._sessions.get(token)
        assert session is not None
        assert session.disconnected_at is not None


class _FirstSendHold:
    def __init__(self, send: Callable[[bytes], Awaitable[None]], order: list[str]) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self._order = order
        self._send = send

    async def send(self, data: bytes) -> None:
        if self.entered.is_set():
            await self._send(data)
            return

        self.entered.set()
        await self.release.wait()
        await self._send(data)
        self._order.append("held_send_done")


async def _let_ready_tasks_run() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


def _track_replacements(manager: SessionManager, order: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    original_replace = manager._game_service.replace_with_ai_player

    def tracking_replace(game_id: str, seat: int) -> None:
        order.append(f"replace seat {seat}")
        return original_replace(game_id, seat)

    monkeypatch.setattr(manager._game_service, "replace_with_ai_player", tracking_replace)


class TestLockBoundaryRaces:
    async def test_lock_boundary__when_leave_arrives_during_action_broadcast__should_replace_after_the_send(
        self, manager, monkeypatch
    ):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        order: list[str] = []
        _track_replacements(manager, order, monkeypatch)
        bob_send = _FirstSendHold(conns[1].send_bytes, order)
        monkeypatch.setattr(conns[1], "send_bytes", bob_send.send)

        action = asyncio.create_task(
            manager.handle_game_action(conns[1], action=GameAction.DISCARD, data={}, wait_id=current_wait_id(manager))
        )
        await bob_send.entered.wait()
        leave = asyncio.create_task(manager.leave_game(conns[0]))
        await _let_ready_tasks_run()
        bob_send.release.set()
        await asyncio.gather(action, leave)
        assert order == ["held_send_done", "replace seat 0"]

    async def test_lock_boundary__when_leave_arrives_during_timeout_broadcast__should_replace_after_the_send(
        self, manager, monkeypatch
    ):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])
        order: list[str] = []
        _track_replacements(manager, order, monkeypatch)
        bob_send = _FirstSendHold(conns[1].send_bytes, order)
        monkeypatch.setattr(conns[1], "send_bytes", bob_send.send)

        timeout = asyncio.create_task(run_timeout(manager, game_id="game1", timeout_type=TimeoutType.TURN, seat=1))
        await bob_send.entered.wait()
        leave = asyncio.create_task(manager.leave_game(conns[0]))
        await _let_ready_tasks_run()
        bob_send.release.set()
        await asyncio.gather(timeout, leave)
        assert order == ["held_send_done", "replace seat 0"]

    async def test_lock_boundary__when_last_player_leaves_twice_concurrently__should_clean_up_once(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        # Alice leaves first (not last)
        await manager.leave_game(conns[0])
        assert manager.get_game("game1") is not None

        cleanup_count = 0
        original_cleanup = manager._game_service.cleanup_game

        def counting_cleanup(game_id):
            nonlocal cleanup_count
            cleanup_count += 1
            return original_cleanup(game_id)

        manager._game_service.cleanup_game = counting_cleanup

        # Bob leaves -- triggers cleanup. Simulate a second leave_game concurrently.
        await asyncio.gather(
            manager.leave_game(conns[1]),
            manager.leave_game(conns[1]),
        )
        assert cleanup_count == 1
        assert manager.get_game("game1") is None

    async def test_lock_boundary__when_ai_replacement_runs_on_leave__should_hold_game_lock(self, manager):
        conns = await create_started_game(manager, player_names=["Alice", "Bob"])

        lock = manager._get_game_lock("game1")
        assert lock is not None

        lock_was_held = False

        def check_lock_process(game_id, seat):
            nonlocal lock_was_held
            # the lock should be held (locked) when this is called
            lock_was_held = lock.locked()
            return mock_update([])

        manager._game_service.process_ai_player_actions_after_replacement = check_lock_process

        await manager.leave_game(conns[0])
        assert lock_was_held is True


class TestHeartbeat:
    async def test_heartbeat__when_ping_received__should_reply_pong_and_update_last_ping(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        initial_time = manager._heartbeat._last_ping.get(conn.connection_id)

        # small delay so monotonic time advances
        await asyncio.sleep(0.01)
        await manager.handle_ping(conn)
        assert len(conn.sent_messages) == 1
        assert conn.sent_messages[0]["type"] == SessionMessageType.PONG
        assert manager._heartbeat._last_ping.get(conn.connection_id) > initial_time
