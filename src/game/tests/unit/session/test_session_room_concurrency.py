import asyncio

import pytest

from game.messaging.types import SessionMessageType
from game.session.manager import SessionManager
from game.tests.mocks import MockConnection, MockGameService


@pytest.fixture
def manager():
    game_service = MockGameService()
    return SessionManager(game_service)


class TestConcurrentSetReady:
    """Tests for concurrent set_ready calls triggering exactly one transition."""

    async def test_concurrent_set_ready_single_transition(self, manager):
        """Two players readying up concurrently trigger exactly one game start."""
        manager.create_room("room1", num_bots=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        # Concurrently set both ready
        await asyncio.gather(
            manager.set_ready(conn1, ready=True),
            manager.set_ready(conn2, ready=True),
        )

        # Room should be gone, game should exist
        assert manager.get_room("room1") is None
        assert manager.get_game("room1") is not None

        # Only one game_starting message per player
        for conn in [conn1, conn2]:
            starting_msgs = [
                m for m in conn.sent_messages if m.get("type") == SessionMessageType.GAME_STARTING
            ]
            assert len(starting_msgs) == 1

    async def test_concurrent_set_ready_four_players(self, manager):
        """Four players readying up concurrently trigger exactly one game start."""
        manager.create_room("room1", num_bots=0)
        conns = [MockConnection() for _ in range(4)]
        for i, conn in enumerate(conns):
            manager.register_connection(conn)
            await manager.join_room(conn, "room1", f"Player{i}", f"tok-{i}")
            conn._outbox.clear()

        # All set ready concurrently
        await asyncio.gather(*(manager.set_ready(conn, ready=True) for conn in conns))

        assert manager.get_room("room1") is None
        assert manager.get_game("room1") is not None

        for conn in conns:
            starting_msgs = [
                m for m in conn.sent_messages if m.get("type") == SessionMessageType.GAME_STARTING
            ]
            assert len(starting_msgs) == 1

    async def test_concurrent_leave_and_ready(self, manager):
        """Leave and ready happening concurrently do not leave stale state."""
        manager.create_room("room1", num_bots=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice", "tok-alice")
        await manager.join_room(conn2, "room1", "Bob", "tok-bob")

        # Alice readies, Bob leaves concurrently
        await asyncio.gather(
            manager.set_ready(conn1, ready=True),
            manager.leave_room(conn2),
        )

        # Room might still exist (Alice ready but alone, not full)
        # or might be cleaned up if Alice also left
        # The key invariant: no stale player references
        assert not manager.is_in_room(conn2.connection_id)
