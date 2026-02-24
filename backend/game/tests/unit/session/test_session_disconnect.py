import asyncio
from unittest.mock import AsyncMock

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, ServiceEvent
from game.messaging.event_payload import EVENT_TYPE_INT
from game.messaging.types import SessionMessageType
from game.tests.mocks import MockConnection, MockResultEvent

from .helpers import create_started_game


class TestSessionManagerDisconnect:
    """Tests for disconnect handling."""

    async def test_disconnect_replaces_player_with_ai_player(self, manager):
        """Disconnecting a player from a started multi-player game calls replace_with_ai_player."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        game = manager.get_game("game1")
        assert game.started is True

        # track replace_with_ai_player calls
        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_with_ai_player = tracking_replace

        await manager.leave_game(conns[0])

        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", "Alice")
        # game should still exist (Bob is still in)
        assert manager.get_game("game1") is not None

    async def test_last_player_disconnect_does_not_replace_with_ai_player(self, manager):
        """When the last player leaves, AI player replacement is skipped and the game is cleaned up."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        game = manager.get_game("game1")
        assert game.started is True

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_with_ai_player = tracking_replace

        # first player leaves (triggers AI player replacement)
        await manager.leave_game(conns[0])
        assert len(replace_calls) == 1

        # second player leaves (last player -- no AI player replacement, game cleaned up)
        await manager.leave_game(conns[1])
        assert len(replace_calls) == 1  # no additional call
        assert manager.get_game("game1") is None

    async def test_disconnect_cancels_player_timer(self, manager):
        """Disconnecting a player cancels their timer in the timers dict."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # verify timers exist for both seats
        assert manager._timer_manager.get_timer("game1", 0) is not None
        assert manager._timer_manager.get_timer("game1", 1) is not None

        await manager.leave_game(conns[0])

        # seat 0's timer should be removed
        assert manager._timer_manager.get_timer("game1", 0) is None
        # seat 1's timer should remain
        assert manager._timer_manager.get_timer("game1", 1) is not None

    async def test_ai_player_replacement_broadcasts_events(self, manager):
        """When AI player replacement produces events, they are broadcast to remaining players."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # make process_ai_player_actions_after_replacement return an event
        ai_player_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="AI",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=[ai_player_event],
        )

        await manager.leave_game(conns[0])

        # Bob should receive the AI player action event
        ai_player_msgs = [m for m in conns[1].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(ai_player_msgs) == 1

    async def test_stale_timeout_after_replacement_is_noop(self, manager):
        """A timeout callback for a replaced player's seat is safely ignored."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # Alice disconnects
        await manager.leave_game(conns[0])
        conns[1]._outbox.clear()

        # stale timeout fires for Alice's old seat (seat 0)
        # should be a no-op because _get_player_at_seat returns None for seat 0
        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

        assert len(conns[1].sent_messages) == 0

    async def test_leave_game_skips_ai_player_replacement_when_lock_missing(self, manager):
        """leave_game skips AI player replacement when the game lock is missing.

        Marks session disconnected instead.
        """
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        player = manager._players.get(conns[0].connection_id)
        token = player.session_token

        # remove the game lock to simulate the startup window where
        # game.started is True but the lock hasn't been created yet
        manager._game_locks.pop("game1", None)

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_with_ai_player = tracking_replace

        # leave_game should skip AI player replacement (no lock) but use started-game
        # session semantics (mark_disconnected, not remove_session)
        await manager.leave_game(conns[0])

        assert len(replace_calls) == 0

        # session should be marked disconnected (not removed) since game.started is True
        session = manager._session_store._sessions.get(token)
        assert session is not None
        assert session.disconnected_at is not None


class TestLockBoundaryRaces:
    """Tests for lock-boundary hardening: disconnect/action/timeout race scenarios."""

    async def test_leave_game_serialized_with_handle_action(self, manager):
        """leave_game and handle_game_action are serialized by the per-game lock."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        execution_order = []

        original_handle = manager._game_service.handle_action
        original_replace = manager._game_service.replace_with_ai_player
        original_process = manager._game_service.process_ai_player_actions_after_replacement

        async def slow_handle_action(game_id, player_name, action, data):
            execution_order.append("action_start")
            result = await original_handle(game_id, player_name, action, data)
            execution_order.append("action_end")
            return result

        def tracking_replace(game_id, player_name):
            execution_order.append("replace_start")
            return original_replace(game_id, player_name)

        async def tracking_process(game_id, seat):
            execution_order.append("process_ai_player")
            return await original_process(game_id, seat)

        manager._game_service.handle_action = slow_handle_action
        manager._game_service.replace_with_ai_player = tracking_replace
        manager._game_service.process_ai_player_actions_after_replacement = tracking_process

        # run action and leave concurrently -- they should be serialized by the lock
        await asyncio.gather(
            manager.handle_game_action(conns[1], GameAction.DISCARD, {}),
            manager.leave_game(conns[0]),
        )

        # both operations completed without errors -- verify they didn't interleave
        if "action_start" in execution_order and "action_end" in execution_order:
            start_idx = execution_order.index("action_start")
            end_idx = execution_order.index("action_end")
            between = execution_order[start_idx : end_idx + 1]
            assert "replace_start" not in between

    async def test_leave_game_serialized_with_timeout(self, manager):
        """leave_game and timeout callback are serialized by the per-game lock."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        execution_order = []

        original_timeout = manager._game_service.handle_timeout
        original_replace = manager._game_service.replace_with_ai_player
        original_process = manager._game_service.process_ai_player_actions_after_replacement

        async def slow_timeout(game_id, player_name, timeout_type):
            execution_order.append("timeout_start")
            result = await original_timeout(game_id, player_name, timeout_type)
            execution_order.append("timeout_end")
            return result

        def tracking_replace(game_id, player_name):
            execution_order.append("replace_start")
            return original_replace(game_id, player_name)

        async def tracking_process(game_id, seat):
            execution_order.append("process_ai_player")
            return await original_process(game_id, seat)

        manager._game_service.handle_timeout = slow_timeout
        manager._game_service.replace_with_ai_player = tracking_replace
        manager._game_service.process_ai_player_actions_after_replacement = tracking_process

        # run timeout and leave concurrently
        await asyncio.gather(
            manager._handle_timeout("game1", TimeoutType.TURN, seat=1),
            manager.leave_game(conns[0]),
        )

        # timeout and leave should be serialized
        if "timeout_start" in execution_order and "timeout_end" in execution_order:
            start_idx = execution_order.index("timeout_start")
            end_idx = execution_order.index("timeout_end")
            between = execution_order[start_idx : end_idx + 1]
            assert "replace_start" not in between

    async def test_double_leave_only_cleans_up_once(self, manager):
        """Two concurrent leave_game calls for the last player clean up exactly once."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

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

        assert cleanup_count <= 1
        assert manager.get_game("game1") is None

    async def test_leave_game_holds_lock_during_ai_player_replacement(self, manager):
        """AI player replacement in leave_game runs under the same lock as action handling."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        lock = manager._get_game_lock("game1")
        assert lock is not None

        lock_was_held = False

        async def check_lock_process(game_id, seat):
            nonlocal lock_was_held
            # the lock should be held (locked) when this is called
            lock_was_held = lock.locked()
            return []

        manager._game_service.process_ai_player_actions_after_replacement = check_lock_process

        await manager.leave_game(conns[0])

        assert lock_was_held is True


class TestHeartbeat:
    """Tests for heartbeat (ping/pong) and per-game heartbeat monitor."""

    async def test_ping_responds_with_pong(self, manager):
        """handle_ping sends a pong message and updates last activity timestamp."""
        conn = MockConnection()
        manager.register_connection(conn)
        initial_time = manager._heartbeat._last_ping.get(conn.connection_id)

        # small delay so monotonic time advances
        await asyncio.sleep(0.01)
        await manager.handle_ping(conn)

        assert len(conn.sent_messages) == 1
        assert conn.sent_messages[0]["type"] == SessionMessageType.PONG
        assert manager._heartbeat._last_ping.get(conn.connection_id) > initial_time
