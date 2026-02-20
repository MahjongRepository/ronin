"""Tests for room TTL expiration and the room reaper task."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from game.server.app import create_app
from game.session.manager import SessionManager
from game.tests.mocks import MockConnection, MockGameService


@pytest.fixture
def manager_with_ttl():
    """SessionManager with a short TTL for testing."""
    game_service = MockGameService()
    return SessionManager(game_service, room_ttl_seconds=60)


@pytest.fixture
def manager_no_ttl():
    """SessionManager with TTL disabled."""
    game_service = MockGameService()
    return SessionManager(game_service, room_ttl_seconds=0)


class TestRoomReaper:
    async def test_reaper_closes_expired_rooms(self, manager_with_ttl):
        """Expired rooms with players get their connections closed and room removed."""
        manager = manager_with_ttl
        room = manager.create_room("room1")

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice")

        # Simulate room created 120 seconds ago (past 60s TTL)
        room.created_at -= 120

        await manager._room_manager._reap_expired_rooms()

        assert conn.is_closed
        assert manager.get_room("room1") is None
        assert manager.room_count == 0

    async def test_reaper_skips_non_expired_rooms(self, manager_with_ttl):
        """Non-expired rooms are left untouched."""
        manager = manager_with_ttl
        manager.create_room("room1")

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice")

        # Room is fresh (created_at is ~now), TTL is 60s
        await manager._room_manager._reap_expired_rooms()

        assert not conn.is_closed

    async def test_reaper_cleans_empty_expired_room(self, manager_with_ttl):
        """Empty expired rooms are removed directly without disconnect."""
        manager = manager_with_ttl
        room = manager.create_room("room1")

        assert room.is_empty
        room.created_at -= 120

        await manager._room_manager._reap_expired_rooms()

        assert manager.get_room("room1") is None
        assert manager.room_count == 0

    async def test_reaper_idempotent_start(self, manager_with_ttl):
        """Calling start_room_reaper twice does not create duplicate tasks."""
        manager = manager_with_ttl
        manager.start_room_reaper()
        task1 = manager._room_manager._room_reaper_task
        manager.start_room_reaper()
        task2 = manager._room_manager._room_reaper_task

        assert task1 is task2

        await manager.stop_room_reaper()

    async def test_reaper_disabled_when_ttl_zero(self, manager_no_ttl):
        """Room reaper does not start when room_ttl_seconds=0."""
        manager = manager_no_ttl
        manager.start_room_reaper()
        assert manager._room_manager._room_reaper_task is None

    async def test_reaper_stops_cleanly(self, manager_with_ttl):
        """stop_room_reaper cancels the background task."""
        manager = manager_with_ttl
        manager.start_room_reaper()
        assert manager._room_manager._room_reaper_task is not None

        await manager.stop_room_reaper()
        assert manager._room_manager._room_reaper_task is None

    async def test_reaper_skips_room_whose_lock_was_removed(self, manager_with_ttl):
        """Reaper skips a candidate room whose lock was already cleaned up."""
        manager = manager_with_ttl
        room = manager.create_room("room1")
        room.created_at -= 120

        # Remove the lock to simulate another coroutine cleaning up the room
        # between the candidate snapshot and per-room processing.
        manager._room_manager._room_locks.pop("room1", None)

        await manager._room_manager._reap_expired_rooms()

        # Room still in _rooms (reaper couldn't acquire lock, so it skipped)
        assert manager.get_room("room1") is room

    async def test_reaper_skips_room_that_started_transitioning(self, manager_with_ttl):
        """Reaper skips a room that began transitioning after the candidate snapshot.

        Uses a lock wrapper to flip transitioning=True on acquire, simulating
        a concurrent set_ready() call between the snapshot and the lock check.
        """
        manager = manager_with_ttl
        rm = manager._room_manager
        room = manager.create_room("room1")

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice")

        room.created_at -= 120

        # Wrap the lock so that acquiring it sets transitioning=True,
        # simulating set_ready() running between snapshot and lock.
        real_lock = rm._room_locks["room1"]

        class _SetTransitioningOnAcquire:
            async def __aenter__(self):
                room.transitioning = True
                return await real_lock.__aenter__()

            async def __aexit__(self, *args):
                return await real_lock.__aexit__(*args)

        rm._room_locks["room1"] = _SetTransitioningOnAcquire()

        await rm._reap_expired_rooms()

        assert not conn.is_closed
        assert manager.get_room("room1") is room

    async def test_reaper_prevents_join_during_close(self, manager_with_ttl):
        """Expired room is removed from _rooms before closing connections,
        preventing new players from joining during the close window."""
        manager = manager_with_ttl
        room = manager.create_room("room1")

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_room(conn, "room1", "Alice")
        room.created_at -= 120

        await manager._room_manager._reap_expired_rooms()

        # Room is already removed; a new join attempt should fail
        new_conn = MockConnection()
        manager.register_connection(new_conn)
        await manager.join_room(new_conn, "room1", "Bob")

        error_msgs = [m for m in new_conn.sent_messages if m.get("type") == "session_error"]
        assert len(error_msgs) == 1
        assert error_msgs[0]["code"] == "room_not_found"

    async def test_reaper_loop_calls_reap(self, manager_with_ttl):
        """The reaper loop calls _reap_expired_rooms after sleeping."""
        rm = manager_with_ttl._room_manager
        rm._reap_expired_rooms = AsyncMock(side_effect=asyncio.CancelledError)

        with (
            patch("game.session.room_manager.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(asyncio.CancelledError),
        ):
            await rm._room_reaper_loop()

        rm._reap_expired_rooms.assert_called_once()

    async def test_reaper_loop_survives_unexpected_error(self, manager_with_ttl):
        """The reaper loop logs and continues when _reap_expired_rooms raises."""
        rm = manager_with_ttl._room_manager
        call_count = 0

        async def fail_then_cancel() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("unexpected")
            raise asyncio.CancelledError

        rm._reap_expired_rooms = AsyncMock(side_effect=fail_then_cancel)

        with (
            patch("game.session.room_manager.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(asyncio.CancelledError),
        ):
            await rm._room_reaper_loop()

        assert call_count == 2


class TestAppReaperLifecycle:
    def test_startup_starts_reaper_and_shutdown_stops_it(self):
        """App startup starts the room reaper; shutdown stops it."""
        sm = SessionManager(MockGameService(), room_ttl_seconds=60)
        app = create_app(game_service=MockGameService(), session_manager=sm)

        with TestClient(app):
            assert sm._room_manager._room_reaper_task is not None

        assert sm._room_manager._room_reaper_task is None
