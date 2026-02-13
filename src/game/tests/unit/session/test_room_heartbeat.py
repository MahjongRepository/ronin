import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, patch

from game.session.heartbeat import HEARTBEAT_TIMEOUT, HeartbeatMonitor
from game.session.room import Room, RoomPlayer
from game.tests.mocks import MockConnection


class TestRoomHeartbeatTaskManagement:
    """Tests for room heartbeat task lifecycle."""

    async def test_start_for_room_creates_task(self):
        monitor = HeartbeatMonitor()

        def get_room(_room_id):
            return None

        monitor.start_for_room("room1", get_room)
        assert "room:room1" in monitor._tasks
        assert monitor._tasks.get("room:room1") is not None

        await monitor.stop_for_room("room1")

    async def test_stop_for_room_removes_task(self):
        monitor = HeartbeatMonitor()

        def get_room(_room_id):
            return None

        monitor.start_for_room("room1", get_room)
        assert "room:room1" in monitor._tasks

        await monitor.stop_for_room("room1")
        assert "room:room1" not in monitor._tasks

    async def test_stop_for_room_nonexistent_is_noop(self):
        monitor = HeartbeatMonitor()
        await monitor.stop_for_room("nonexistent")
        assert "room:nonexistent" not in monitor._tasks


class TestRoomHeartbeatLoop:
    """Tests for the room heartbeat check loop."""

    async def test_room_loop_disconnects_stale_connection(self):
        """Stale room connections are closed when past the heartbeat timeout."""
        monitor = HeartbeatMonitor()
        conn = MockConnection()
        monitor.record_connect(conn.connection_id)

        monitor._last_ping[conn.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        room = Room(room_id="room1")
        rp = RoomPlayer(connection=conn, name="Alice", room_id="room1", session_token="tok")
        room.players[conn.connection_id] = rp

        def get_room(room_id):
            return room if room_id == "room1" else None

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await monitor._check_loop("room1", "room", get_room)

        assert conn.is_closed
        assert conn._close_code == 1000
        assert conn._close_reason == "heartbeat_timeout"

    async def test_room_loop_keeps_active_connection(self):
        """Active room connections are not disconnected."""
        monitor = HeartbeatMonitor()
        conn = MockConnection()
        monitor.record_connect(conn.connection_id)

        room = Room(room_id="room1")
        rp = RoomPlayer(connection=conn, name="Alice", room_id="room1", session_token="tok")
        room.players[conn.connection_id] = rp

        def get_room(room_id):
            return room if room_id == "room1" else None

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await monitor._check_loop("room1", "room", get_room)

        assert not conn.is_closed

    async def test_room_loop_stops_when_room_is_none(self):
        """Room loop exits when get_room returns None."""
        monitor = HeartbeatMonitor()

        def get_room(_room_id):
            return None

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.return_value = None
            await monitor._check_loop("room1", "room", get_room)

        mock_sleep.assert_called_once()

    async def test_room_loop_handles_connection_error_gracefully(self):
        """Connection errors during close in room loop are suppressed."""
        monitor = HeartbeatMonitor()
        conn = MockConnection()
        monitor.record_connect(conn.connection_id)

        monitor._last_ping[conn.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        room = Room(room_id="room1")
        rp = RoomPlayer(connection=conn, name="Alice", room_id="room1", session_token="tok")
        room.players[conn.connection_id] = rp

        def get_room(room_id):
            return room if room_id == "room1" else None

        failing_close = AsyncMock(side_effect=ConnectionError("connection lost"))
        conn.close = failing_close  # type: ignore[assignment]

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await monitor._check_loop("room1", "room", get_room)

    async def test_room_loop_checks_multiple_players(self):
        """Room loop checks all players and disconnects only stale ones."""
        monitor = HeartbeatMonitor()
        conn1 = MockConnection()
        conn2 = MockConnection()
        monitor.record_connect(conn1.connection_id)
        monitor.record_connect(conn2.connection_id)

        monitor._last_ping[conn1.connection_id] = time.monotonic() - HEARTBEAT_TIMEOUT - 10

        room = Room(room_id="room1", num_bots=2)
        rp1 = RoomPlayer(connection=conn1, name="Alice", room_id="room1", session_token="tok-a")
        rp2 = RoomPlayer(connection=conn2, name="Bob", room_id="room1", session_token="tok-b")
        room.players[conn1.connection_id] = rp1
        room.players[conn2.connection_id] = rp2

        def get_room(room_id):
            return room if room_id == "room1" else None

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]
            with contextlib.suppress(asyncio.CancelledError):
                await monitor._check_loop("room1", "room", get_room)

        assert conn1.is_closed
        assert not conn2.is_closed


class TestNamespaceSeparation:
    """Room and game tasks use separate namespace keys."""

    async def test_room_and_game_coexist(self):
        monitor = HeartbeatMonitor()

        def get_room(_id):
            return None

        def get_game(_id):
            return None

        monitor.start_for_room("test1", get_room)
        monitor.start_for_game("test1", get_game)

        assert "room:test1" in monitor._tasks
        assert "game:test1" in monitor._tasks

        await monitor.stop_for_room("test1")
        assert "room:test1" not in monitor._tasks
        assert "game:test1" in monitor._tasks

        await monitor.stop_for_game("test1")
        assert "game:test1" not in monitor._tasks
