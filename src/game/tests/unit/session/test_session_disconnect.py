import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, patch

from game.logic.enums import GameAction, TimeoutType
from game.messaging.events import EventType, ServiceEvent
from game.messaging.types import SessionMessageType
from game.session.manager import HEARTBEAT_TIMEOUT
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
        assert 0 in manager._timers["game1"]
        assert 1 in manager._timers["game1"]

        await manager.leave_game(conns[0])

        # seat 0's timer should be removed from the dict
        assert 0 not in manager._timers["game1"]
        # seat 1's timer should remain
        assert 1 in manager._timers["game1"]

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
            target="all",
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

        async def disconnecting_start(game_id, player_names):
            result = await original_start(game_id, player_names)
            # simulate Alice disconnecting during start_game
            for conn_id, player in list(game.players.items()):
                if player.name == "Alice":
                    game.players.pop(conn_id)
                    player.game_id = None
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

        async def late_disconnecting_start(game_id, player_names):
            return await original_start(game_id, player_names)

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
            target="all",
        )
        manager._game_service.process_bot_actions_after_replacement = AsyncMock(return_value=[bot_event])

        # join Bob -- triggers start; Alice is removed during first broadcast
        await manager.join_game(conns[1], "game1", "Bob")

        # Bob should receive the bot action event
        bot_msgs = [m for m in conns[1].sent_messages if m.get("type") == EventType.DRAW]
        assert len(bot_msgs) == 1

    async def test_replace_with_bot_returns_when_lock_missing(self, manager):
        """_replace_with_bot returns early when game lock has been cleaned up."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        game = manager.get_game("game1")

        # remove the game lock to simulate cleanup race
        manager._game_locks.pop("game1", None)

        process_calls = []
        original_process = manager._game_service.process_bot_actions_after_replacement

        async def tracking_process(game_id, seat):
            process_calls.append((game_id, seat))
            return await original_process(game_id, seat)

        manager._game_service.process_bot_actions_after_replacement = tracking_process

        # directly call _replace_with_bot (lock is missing)
        await manager._replace_with_bot(game, "Alice", 0)

        # replace_player_with_bot was called but process_bot_actions was NOT
        # (early return due to missing lock)
        assert len(process_calls) == 0


class TestHeartbeat:
    """Tests for heartbeat (ping/pong) and per-game heartbeat monitor."""

    async def test_ping_responds_with_pong(self, manager):
        """handle_ping sends a pong message and updates last activity timestamp."""
        conn = MockConnection()
        manager.register_connection(conn)
        initial_time = manager._last_ping[conn.connection_id]

        # small delay so monotonic time advances
        await asyncio.sleep(0.01)
        await manager.handle_ping(conn)

        assert len(conn.sent_messages) == 1
        assert conn.sent_messages[0]["type"] == SessionMessageType.PONG
        assert manager._last_ping[conn.connection_id] > initial_time

    async def test_unregister_connection_cleans_up_ping_tracking(self, manager):
        """unregister_connection removes ping tracking."""
        conn = MockConnection()
        manager.register_connection(conn)
        assert conn.connection_id in manager._last_ping

        manager.unregister_connection(conn)
        assert conn.connection_id not in manager._last_ping

    async def test_heartbeat_monitor_disconnects_stale_connection(self, manager):
        """Heartbeat monitor disconnects connections that haven't pinged within timeout."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")

        game = manager.get_game("game1")
        assert game is not None

        # set the last ping to well past the timeout
        manager._last_ping[conn.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        # manually add the game to internal state (bypass start for this test)
        # and run one iteration of the heartbeat check
        with patch("game.session.manager.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await manager._heartbeat_loop("game1")

        assert conn.is_closed

    async def test_heartbeat_monitor_keeps_active_connections(self, manager):
        """Heartbeat monitor does not disconnect connections with recent pings."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")

        # last ping is fresh (just registered)
        with patch("game.session.manager.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await manager._heartbeat_loop("game1")

        assert not conn.is_closed
