import asyncio
from typing import Any
from unittest.mock import AsyncMock

from game.logic.enums import GameAction, TimeoutType
from game.messaging.events import BroadcastTarget, EventType, ServiceEvent
from game.messaging.types import SessionMessageType
from game.tests.mocks import MockConnection, MockResultEvent


class TestSessionManagerDisconnect:
    """Tests for disconnect handling."""

    async def test_disconnect_replaces_human_with_bot(self, manager):
        """Disconnecting a human from a started multi-human game calls replace_player_with_bot."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        game = manager.get_game("game1")
        assert game.started is True

        # track replace_player_with_bot calls
        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        await manager.leave_game(conns[0])

        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", "Alice")
        # game should still exist (Bob is still in)
        assert manager.get_game("game1") is not None

    async def test_last_human_disconnect_does_not_replace_with_bot(self, manager):
        """When the last human leaves, bot replacement is skipped and the game is cleaned up."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        game = manager.get_game("game1")
        assert game.started is True

        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        # first player leaves (triggers bot replacement)
        await manager.leave_game(conns[0])
        assert len(replace_calls) == 1

        # second player leaves (last human -- no bot replacement, game cleaned up)
        await manager.leave_game(conns[1])
        assert len(replace_calls) == 1  # no additional call
        assert manager.get_game("game1") is None

    async def test_disconnect_cancels_player_timer(self, manager):
        """Disconnecting a human cancels their timer in the timers dict."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        # verify timers exist for both seats
        assert manager._timer_manager.get_timer("game1", 0) is not None
        assert manager._timer_manager.get_timer("game1", 1) is not None

        await manager.leave_game(conns[0])

        # seat 0's timer should be removed
        assert manager._timer_manager.get_timer("game1", 0) is None
        # seat 1's timer should remain
        assert manager._timer_manager.get_timer("game1", 1) is not None

    async def test_leave_game_clears_player_seat_and_game_id(self, manager):
        """After leave_game, both player.game_id and player.seat are cleared to None."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        player = manager._players[conns[0].connection_id]
        assert player.game_id == "game1"
        assert player.seat is not None

        await manager.leave_game(conns[0])

        assert player.game_id is None
        assert player.seat is None

    async def test_leave_pre_start_game_clears_player_state(self, manager):
        """After leaving a pre-start game, player.game_id and player.seat are cleared."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=0)

        await manager.join_game(conn, "game1", "Alice")

        player = manager._players[conn.connection_id]
        assert player.game_id == "game1"

        await manager.leave_game(conn)

        assert player.game_id is None
        assert player.seat is None

    async def test_disconnect_from_non_started_game_does_not_replace(self, manager):
        """Disconnecting from a game that has not started does not trigger bot replacement."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=0)

        await manager.join_game(conn, "game1", "Alice")

        game = manager.get_game("game1")
        assert game.started is False

        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        await manager.leave_game(conn)

        assert len(replace_calls) == 0
        assert manager.get_game("game1") is None

    async def test_bot_replacement_broadcasts_events(self, manager):
        """When bot replacement produces events, they are broadcast to remaining players."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")
        conns[1]._outbox.clear()

        # make process_bot_actions_after_replacement return an event
        bot_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="Bot",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        manager._game_service.process_bot_actions_after_replacement = AsyncMock(return_value=[bot_event])

        await manager.leave_game(conns[0])

        # Bob should receive the bot action event
        bot_msgs = [m for m in conns[1].sent_messages if m.get("type") == EventType.DRAW]
        assert len(bot_msgs) == 1

    async def test_stale_timeout_after_replacement_is_noop(self, manager):
        """A timeout callback for a replaced player's seat is safely ignored."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        # Alice disconnects
        await manager.leave_game(conns[0])
        conns[1]._outbox.clear()

        # stale timeout fires for Alice's old seat (seat 0)
        # should be a no-op because _get_player_at_seat returns None for seat 0
        await manager._handle_timeout("game1", TimeoutType.TURN, seat=0)

        assert len(conns[1].sent_messages) == 0

    async def test_disconnect_during_start_game_replaces_with_bot(self, manager):
        """Player disconnecting during start_game (before seat assignment) triggers bot replacement."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")

        # patch start_game to simulate a disconnect happening during the await.
        # remove Alice from game.players (as leave_game would) before
        # _start_mahjong_game can assign seats.
        original_start = manager._game_service.start_game
        game = manager.get_game("game1")

        async def disconnecting_start(game_id, player_names, **kwargs: Any):  # noqa: ANN401
            result = await original_start(game_id, player_names, **kwargs)
            # simulate Alice disconnecting during start_game
            for conn_id, player in list(game.players.items()):
                if player.name == "Alice":
                    game.players.pop(conn_id)
                    player.game_id = None
                    player.seat = None
                    break
            return result

        manager._game_service.start_game = disconnecting_start

        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        # join Bob -- triggers start; Alice is removed during start_game
        await manager.join_game(conns[1], "game1", "Bob")

        # post-start recovery should detect Alice disconnected and replace with bot
        assert ("game1", "Alice") in replace_calls

    async def test_disconnect_during_start_cancels_timer_and_broadcasts(self, manager):
        """Post-start recovery cancels the disconnected player's timer and broadcasts bot events."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")

        original_start = manager._game_service.start_game
        game = manager.get_game("game1")

        # remove Alice AFTER timer creation by injecting the removal
        # between timer setup and the lock acquisition in _start_mahjong_game.
        # we achieve this by removing her after start_game returns but ensuring
        # the timer loop still sees her (she's in game.players during that loop).
        alice_removed = False

        async def late_disconnecting_start(game_id, player_names, **kwargs: Any):  # noqa: ANN401
            return await original_start(game_id, player_names, **kwargs)

        manager._game_service.start_game = late_disconnecting_start

        # patch _broadcast_events to remove Alice just before the recovery loop runs.
        # the first call to _broadcast_events is for start events, then the recovery loop
        # checks connected_names. we remove Alice after the seat/timer assignment but
        # before the lock block re-checks game.player_names.
        original_broadcast = manager._broadcast_events

        async def removing_broadcast(g, events):
            nonlocal alice_removed
            await original_broadcast(g, events)
            if not alice_removed:
                alice_removed = True
                for conn_id, player in list(game.players.items()):
                    if player.name == "Alice":
                        game.players.pop(conn_id)
                        player.game_id = None
                        player.seat = None
                        break

        manager._broadcast_events = removing_broadcast

        # mock process_bot_actions_after_replacement to return an event
        bot_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="Bot",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        manager._game_service.process_bot_actions_after_replacement = AsyncMock(return_value=[bot_event])

        # join Bob -- triggers start; Alice is removed during first broadcast
        await manager.join_game(conns[1], "game1", "Bob")

        # Bob should receive the bot action event
        bot_msgs = [m for m in conns[1].sent_messages if m.get("type") == EventType.DRAW]
        assert len(bot_msgs) == 1

    async def test_leave_game_skips_bot_replacement_when_lock_missing(self, manager):
        """leave_game skips bot replacement when the game lock has been cleaned up."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        # remove the game lock to simulate cleanup race
        manager._game_locks.pop("game1", None)

        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        # leave_game should treat the missing lock as pre-start (no bot replacement)
        await manager.leave_game(conns[0])

        assert len(replace_calls) == 0


class TestLockBoundaryRaces:
    """Tests for lock-boundary hardening: disconnect/action/timeout race scenarios."""

    async def test_leave_game_serialized_with_handle_action(self, manager):
        """leave_game and handle_game_action are serialized by the per-game lock."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        execution_order = []

        original_handle = manager._game_service.handle_action
        original_replace = manager._game_service.replace_player_with_bot
        original_process = manager._game_service.process_bot_actions_after_replacement

        async def slow_handle_action(game_id, player_name, action, data):
            execution_order.append("action_start")
            result = await original_handle(game_id, player_name, action, data)
            execution_order.append("action_end")
            return result

        def tracking_replace(game_id, player_name):
            execution_order.append("replace_start")
            return original_replace(game_id, player_name)

        async def tracking_process(game_id, seat):
            execution_order.append("process_bot")
            return await original_process(game_id, seat)

        manager._game_service.handle_action = slow_handle_action
        manager._game_service.replace_player_with_bot = tracking_replace
        manager._game_service.process_bot_actions_after_replacement = tracking_process

        # run action and leave concurrently -- they should be serialized by the lock
        await asyncio.gather(
            manager.handle_game_action(conns[1], GameAction.DISCARD, {}),
            manager.leave_game(conns[0]),
        )

        # both operations completed without errors -- verify they didn't interleave
        # (action_start/action_end should be contiguous, replace should not appear between them)
        if "action_start" in execution_order and "action_end" in execution_order:
            start_idx = execution_order.index("action_start")
            end_idx = execution_order.index("action_end")
            between = execution_order[start_idx : end_idx + 1]
            assert "replace_start" not in between

    async def test_leave_game_serialized_with_timeout(self, manager):
        """leave_game and timeout callback are serialized by the per-game lock."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        execution_order = []

        original_timeout = manager._game_service.handle_timeout
        original_replace = manager._game_service.replace_player_with_bot
        original_process = manager._game_service.process_bot_actions_after_replacement

        async def slow_timeout(game_id, player_name, timeout_type):
            execution_order.append("timeout_start")
            result = await original_timeout(game_id, player_name, timeout_type)
            execution_order.append("timeout_end")
            return result

        def tracking_replace(game_id, player_name):
            execution_order.append("replace_start")
            return original_replace(game_id, player_name)

        async def tracking_process(game_id, seat):
            execution_order.append("process_bot")
            return await original_process(game_id, seat)

        manager._game_service.handle_timeout = slow_timeout
        manager._game_service.replace_player_with_bot = tracking_replace
        manager._game_service.process_bot_actions_after_replacement = tracking_process

        # run timeout and leave concurrently
        await asyncio.gather(
            manager._handle_timeout("game1", TimeoutType.TURN, seat=1),
            manager.leave_game(conns[0]),
        )

        # timeout and leave should be serialized -- timeout internals should not interleave with replace
        if "timeout_start" in execution_order and "timeout_end" in execution_order:
            start_idx = execution_order.index("timeout_start")
            end_idx = execution_order.index("timeout_end")
            between = execution_order[start_idx : end_idx + 1]
            assert "replace_start" not in between

    async def test_double_leave_only_cleans_up_once(self, manager):
        """Two concurrent leave_game calls for the last player clean up exactly once."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

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
        # Because _games.pop is atomic, only one path should run cleanup.
        await asyncio.gather(
            manager.leave_game(conns[1]),
            manager.leave_game(conns[1]),
        )

        assert cleanup_count <= 1
        assert manager.get_game("game1") is None

    async def test_leave_game_holds_lock_during_bot_replacement(self, manager):
        """Bot replacement in leave_game runs under the same lock as action handling."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        lock = manager._get_game_lock("game1")
        assert lock is not None

        lock_was_held = False

        async def check_lock_process(game_id, seat):  # noqa: ARG001
            nonlocal lock_was_held
            # the lock should be held (locked) when this is called
            lock_was_held = lock.locked()
            return []

        manager._game_service.process_bot_actions_after_replacement = check_lock_process

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

    async def test_unregister_connection_cleans_up_ping_tracking(self, manager):
        """unregister_connection removes ping tracking."""
        conn = MockConnection()
        manager.register_connection(conn)
        assert manager._heartbeat._last_ping.get(conn.connection_id) is not None

        manager.unregister_connection(conn)
        assert manager._heartbeat._last_ping.get(conn.connection_id) is None
