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

    async def test_join_game_adds_player(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        game = manager.get_game("game1")
        assert game is not None
        assert game.player_count == 1
        assert "Alice" in game.player_names

    async def test_join_game_notifies_player(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == ServerMessageType.GAME_JOINED

    async def test_second_player_notifies_first(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # conn1 should have received: game_joined + player_joined
        assert len(conn1.sent_messages) == 2
        assert conn1.sent_messages[1]["type"] == ServerMessageType.PLAYER_JOINED
        assert conn1.sent_messages[1]["player_name"] == "Bob"

    async def test_leave_game_notifies_others(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # clear previous messages
        conn1._outbox.clear()

        await manager.leave_game(conn2)

        assert len(conn1.sent_messages) == 1
        assert conn1.sent_messages[0]["type"] == ServerMessageType.PLAYER_LEFT
        assert conn1.sent_messages[0]["player_name"] == "Bob"

    async def test_game_full_error(self, manager):
        connections = [MockConnection() for _ in range(5)]
        for conn in connections:
            manager.register_connection(conn)
        manager.create_game("game1")

        # join 4 players (max)
        for i, conn in enumerate(connections[:4]):
            await manager.join_game(conn, "game1", f"Player{i}")

        # 5th player should get error
        await manager.join_game(connections[4], "game1", "Player4")

        msg = connections[4].sent_messages[0]
        assert msg["type"] == ServerMessageType.ERROR
        assert msg["code"] == "game_full"

    async def test_duplicate_name_error(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Alice")

        msg = conn2.sent_messages[0]
        assert msg["type"] == ServerMessageType.ERROR
        assert msg["code"] == "name_taken"

    async def test_empty_game_is_cleaned_up(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        assert manager.get_game("game1") is not None

        await manager.leave_game(conn)
        assert manager.get_game("game1") is None

    async def test_join_nonexistent_game_returns_error(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.join_game(conn, "nonexistent", "Alice")

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == ServerMessageType.ERROR
        assert msg["code"] == "game_not_found"
