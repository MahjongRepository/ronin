import pytest

from game.logic.mock import MockGameService
from game.messaging.mock import MockConnection
from game.messaging.types import ServerMessageType
from game.session.manager import SessionManager


class TestSessionManager:
    @pytest.fixture
    def manager(self):
        game_service = MockGameService()
        return SessionManager(game_service)

    async def test_join_room_creates_room(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice")

        room = manager.get_room("room1")
        assert room is not None
        assert room.player_count == 1
        assert "Alice" in room.player_names

    async def test_join_room_notifies_player(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice")

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == ServerMessageType.ROOM_JOINED

    async def test_second_player_notifies_first(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice")
        await manager.join_room(conn2, "room1", "Bob")

        # conn1 should have received: room_joined + player_joined
        assert len(conn1.sent_messages) == 2
        assert conn1.sent_messages[1]["type"] == ServerMessageType.PLAYER_JOINED
        assert conn1.sent_messages[1]["player_name"] == "Bob"

    async def test_leave_room_notifies_others(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice")
        await manager.join_room(conn2, "room1", "Bob")

        # clear previous messages
        conn1._outbox.clear()

        await manager.leave_room(conn2)

        assert len(conn1.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == ServerMessageType.PLAYER_LEFT
        assert conn1.sent_messages[0]["player_name"] == "Bob"

    async def test_room_full_error(self, manager):
        connections = [MockConnection() for _ in range(5)]
        for conn in connections:
            manager.register_connection(conn)

        # join 4 players (max)
        for i, conn in enumerate(connections[:4]):
            await manager.join_room(conn, "room1", f"Player{i}")

        # 5th player should get error
        await manager.join_room(connections[4], "room1", "Player4")

        msg = connections[4].sent_messages[0]
        assert msg["type"] == ServerMessageType.ERROR
        assert msg["code"] == "room_full"

    async def test_duplicate_name_error(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "room1", "Alice")
        await manager.join_room(conn2, "room1", "Alice")

        msg = conn2.sent_messages[0]
        assert msg["type"] == ServerMessageType.ERROR
        assert msg["code"] == "name_taken"

    async def test_empty_room_is_cleaned_up(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_room(conn, "room1", "Alice")
        assert manager.get_room("room1") is not None

        await manager.leave_room(conn)
        assert manager.get_room("room1") is None
