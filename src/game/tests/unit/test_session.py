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

        # first message is game_joined, then game_started event from start_game
        assert len(conn.sent_messages) >= 1
        msg = conn.sent_messages[0]
        assert msg["type"] == ServerMessageType.GAME_JOINED

    async def test_join_game_starts_game_on_first_player(self, manager):
        """When first player joins, start_game is called and game_started events are sent."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        # should receive: game_joined + game_started event (seat_0 only sent to first player)
        game_event_msgs = [m for m in conn.sent_messages if m.get("type") == ServerMessageType.GAME_EVENT]
        assert len(game_event_msgs) >= 1
        # the mock returns game_started events for each seat
        game_started_events = [m for m in game_event_msgs if m.get("event") == "game_started"]
        assert len(game_started_events) == 1  # seat_0 targeted to first player

    async def test_second_player_notifies_first(self, manager):
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # conn1 should have received: game_joined + game_started + player_joined
        player_joined_msgs = [
            m for m in conn1.sent_messages if m.get("type") == ServerMessageType.PLAYER_JOINED
        ]
        assert len(player_joined_msgs) == 1
        assert player_joined_msgs[0]["player_name"] == "Bob"

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

    async def test_handle_game_action_broadcasts_events(self, manager):
        """handle_game_action processes list of events and broadcasts them."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        await manager.handle_game_action(conn, "test_action", {"key": "value"})

        # mock service returns one event with target "all"
        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == ServerMessageType.GAME_EVENT
        assert msg["event"] == "test_action_result"

    async def test_targeted_events_only_sent_to_target_player(self, manager):
        """Events with seat_N target go only to the player at that seat."""
        conn1 = MockConnection()
        manager.register_connection(conn1)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")

        # when first player joins, start_game returns events for all seats,
        # but only seat_0 event reaches conn1 (the only connected player)
        conn1_game_started = [
            m
            for m in conn1.sent_messages
            if m.get("type") == ServerMessageType.GAME_EVENT and m.get("event") == "game_started"
        ]

        # conn1 (seat 0) should only get seat_0 event
        assert len(conn1_game_started) == 1
        assert conn1_game_started[0]["data"]["seat"] == 0

    async def test_broadcast_events_sends_all_target_to_everyone(self, manager):
        """Events with 'all' target are broadcast to all players."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")
        conn1._outbox.clear()
        conn2._outbox.clear()

        # perform action that generates broadcast event
        await manager.handle_game_action(conn1, "test_action", {})

        # both players should receive the event
        assert len(conn1.sent_messages) == 1
        assert len(conn2.sent_messages) == 1
        assert conn1.sent_messages[0]["event"] == "test_action_result"
        assert conn2.sent_messages[0]["event"] == "test_action_result"

    async def test_start_game_not_called_on_second_player(self, manager):
        """start_game is called once when first player joins, not on subsequent joins."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1")

        await manager.join_game(conn1, "game1", "Alice")

        conn1._outbox.clear()
        await manager.join_game(conn2, "game1", "Bob")

        # conn1 should not receive any new game_started events
        new_game_started = [
            m
            for m in conn1.sent_messages
            if m.get("type") == ServerMessageType.GAME_EVENT and m.get("event") == "game_started"
        ]
        assert len(new_game_started) == 0
