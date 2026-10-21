import asyncio
from unittest.mock import AsyncMock

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, ServiceEvent
from game.messaging.types import SessionMessageType
from game.tests.mocks import MockConnection, MockResultEvent
from game.wire.events import EVENT_TYPE_INT

from .helpers import create_started_game


class TestSessionManagerDisconnect:
    async def test_disconnect__when_one_of_two_humans_leaves__should_replace_with_ai_and_keep_game(self, manager):
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

    async def test_disconnect__when_last_human_leaves__should_not_replace_with_ai_and_clean_up_game(self, manager):
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

    async def test_disconnect__when_player_leaves__should_remove_only_their_timer(self, manager):
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # verify timers exist for both seats
        assert manager._timer_manager.get_timer("game1", 0) is not None
        assert manager._timer_manager.get_timer("game1", 1) is not None

        await manager.leave_game(conns[0])

        # seat 0's timer should be removed
        assert manager._timer_manager.get_timer("game1", 0) is None
        # seat 1's timer should remain
        assert manager._timer_manager.get_timer("game1", 1) is not None

    async def test_disconnect__when_ai_replacement_produces_events__should_broadcast_them(self, manager):
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

    async def test_disconnect__when_stale_timeout_fires_for_replaced_seat__should_send_nothing(self, manager):
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # Alice disconnects
        await manager.leave_game(conns[0])
        conns[1]._outbox.clear()

        # stale timeout fires for Alice's old seat (seat 0)
        # should be a no-op because _get_player_at_seat returns None for seat 0
        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

        assert len(conns[1].sent_messages) == 0

    async def test_disconnect__when_game_lock_missing__should_skip_ai_replacement_and_mark_session_disconnected(
        self, manager
    ):
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
    async def test_lock_boundary__when_leave_races_game_action__should_not_replace_mid_action(self, manager):
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        execution_order = []

        original_handle = manager._game_service.handle_action
        original_replace = manager._game_service.replace_with_ai_player
        original_process = manager._game_service.process_ai_player_actions_after_replacement

        async def slow_handle_action(game_id, player_name, action, data):
            execution_order.append("action_start")
            await asyncio.sleep(0)
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

        assert execution_order == ["action_start", "action_end", "replace_start", "process_ai_player"]

    async def test_lock_boundary__when_leave_races_timeout__should_not_replace_mid_timeout(self, manager):
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        execution_order = []

        original_timeout = manager._game_service.handle_timeout
        original_replace = manager._game_service.replace_with_ai_player
        original_process = manager._game_service.process_ai_player_actions_after_replacement

        async def slow_timeout(game_id, player_name, timeout_type):
            execution_order.append("timeout_start")
            await asyncio.sleep(0)
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

        assert execution_order == ["timeout_start", "timeout_end", "replace_start", "process_ai_player"]

    async def test_lock_boundary__when_last_player_leaves_twice_concurrently__should_clean_up_once(self, manager):
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

        assert cleanup_count == 1
        assert manager.get_game("game1") is None

    async def test_lock_boundary__when_ai_replacement_runs_on_leave__should_hold_game_lock(self, manager):
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
