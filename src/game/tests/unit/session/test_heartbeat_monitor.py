import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, patch

from game.session.heartbeat import HEARTBEAT_TIMEOUT, HeartbeatMonitor
from game.session.models import Game, Player
from game.tests.mocks import MockConnection


class TestHeartbeatMonitorRecordConnect:
    """Tests for connection tracking."""

    def test_record_connect_stores_timestamp(self):
        monitor = HeartbeatMonitor()
        monitor.record_connect("conn1")
        assert monitor._last_ping.get("conn1") is not None

    def test_record_connect_multiple_connections(self):
        monitor = HeartbeatMonitor()
        monitor.record_connect("conn1")
        monitor.record_connect("conn2")
        assert monitor._last_ping.get("conn1") is not None
        assert monitor._last_ping.get("conn2") is not None


class TestHeartbeatMonitorRecordDisconnect:
    """Tests for disconnect cleanup."""

    def test_record_disconnect_removes_tracking(self):
        monitor = HeartbeatMonitor()
        monitor.record_connect("conn1")
        assert monitor._last_ping.get("conn1") is not None

        monitor.record_disconnect("conn1")
        assert monitor._last_ping.get("conn1") is None

    def test_record_disconnect_unknown_connection_is_noop(self):
        monitor = HeartbeatMonitor()
        monitor.record_disconnect("unknown")
        assert monitor._last_ping.get("unknown") is None


class TestHeartbeatMonitorRecordPing:
    """Tests for ping timestamp updates."""

    def test_record_ping_updates_timestamp(self):
        monitor = HeartbeatMonitor()
        monitor.record_connect("conn1")
        initial = monitor._last_ping.get("conn1")
        assert initial is not None

        # record_ping should update the timestamp
        monitor.record_ping("conn1")
        updated = monitor._last_ping.get("conn1")
        assert updated is not None
        assert updated >= initial


class TestHeartbeatMonitorTaskManagement:
    """Tests for game task management."""

    async def test_start_for_game_creates_task(self):
        monitor = HeartbeatMonitor()

        def get_game(_game_id):
            return None  # will cause loop to exit

        monitor.start_for_game("game1", get_game)
        assert "game1" in monitor._tasks
        assert monitor._tasks.get("game1") is not None

        # clean up
        await monitor.stop_for_game("game1")

    async def test_stop_for_game_removes_task(self):
        monitor = HeartbeatMonitor()

        def get_game(_game_id):
            return None

        monitor.start_for_game("game1", get_game)
        assert "game1" in monitor._tasks

        await monitor.stop_for_game("game1")
        assert "game1" not in monitor._tasks

    async def test_stop_for_game_nonexistent_is_noop(self):
        monitor = HeartbeatMonitor()
        await monitor.stop_for_game("nonexistent")
        assert "nonexistent" not in monitor._tasks


class TestHeartbeatMonitorLoop:
    """Tests for the heartbeat check loop."""

    async def test_loop_disconnects_stale_connection(self):
        """Stale connections are closed when past the heartbeat timeout."""
        monitor = HeartbeatMonitor()
        conn = MockConnection()
        monitor.record_connect(conn.connection_id)

        # set ping to past timeout
        monitor._last_ping[conn.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        game = Game(game_id="game1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="game1", seat=0)
        game.players[conn.connection_id] = player

        def get_game(game_id):
            return game if game_id == "game1" else None

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await monitor._loop("game1", get_game)

        assert conn.is_closed
        assert conn._close_code == 1000
        assert conn._close_reason == "heartbeat_timeout"

    async def test_loop_keeps_active_connection(self):
        """Active connections are not disconnected."""
        monitor = HeartbeatMonitor()
        conn = MockConnection()
        monitor.record_connect(conn.connection_id)

        game = Game(game_id="game1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="game1", seat=0)
        game.players[conn.connection_id] = player

        def get_game(game_id):
            return game if game_id == "game1" else None

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await monitor._loop("game1", get_game)

        assert not conn.is_closed

    async def test_loop_stops_when_game_is_none(self):
        """Loop exits when get_game returns None."""
        monitor = HeartbeatMonitor()

        def get_game(_game_id):
            return None

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.return_value = None
            # should exit cleanly
            await monitor._loop("game1", get_game)

        # verify sleep was called (loop attempted one iteration)
        mock_sleep.assert_called_once()

    async def test_loop_handles_connection_error_gracefully(self):
        """Connection errors during close are suppressed."""
        monitor = HeartbeatMonitor()
        conn = MockConnection()
        monitor.record_connect(conn.connection_id)

        # set ping to past timeout
        monitor._last_ping[conn.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        game = Game(game_id="game1")
        player = Player(connection=conn, name="Alice", session_token="tok-alice", game_id="game1", seat=0)
        game.players[conn.connection_id] = player

        def get_game(game_id):
            return game if game_id == "game1" else None

        # make close raise a ConnectionError
        failing_close = AsyncMock(side_effect=ConnectionError("connection lost"))
        conn.close = failing_close  # type: ignore[assignment]

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await monitor._loop("game1", get_game)

        # should not raise -- error is suppressed

    async def test_loop_checks_multiple_players(self):
        """Loop checks all players in the game."""
        monitor = HeartbeatMonitor()
        conn1 = MockConnection()
        conn2 = MockConnection()
        monitor.record_connect(conn1.connection_id)
        monitor.record_connect(conn2.connection_id)

        # conn1 is stale, conn2 is fresh
        monitor._last_ping[conn1.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        game = Game(game_id="game1")
        player1 = Player(connection=conn1, name="Alice", session_token="tok-alice", game_id="game1", seat=0)
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="game1", seat=1)
        game.players[conn1.connection_id] = player1
        game.players[conn2.connection_id] = player2

        def get_game(game_id):
            return game if game_id == "game1" else None

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await monitor._loop("game1", get_game)

        assert conn1.is_closed
        assert not conn2.is_closed
