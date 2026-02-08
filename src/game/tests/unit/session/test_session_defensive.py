from unittest.mock import AsyncMock

from game.logic.enums import GameAction, GameErrorCode
from game.logic.events import BroadcastTarget, ErrorEvent, EventType, ServiceEvent
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.tests.mocks import MockConnection


class TestSessionManagerDefensiveChecks:
    """Tests for defensive checks that guard against invalid state."""

    async def test_join_game_already_in_game_returns_error(self, manager):
        """Joining a second game while already in one returns an error."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        manager.create_game("game2")

        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        await manager.join_game(conn, "game2", "Alice")

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.ALREADY_IN_GAME

    async def test_leave_game_when_game_is_none(self, manager):
        """Leaving when the game mapping is missing does not raise."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        # remove the game from the internal mapping to simulate the defensive case
        player = manager._players[conn.connection_id]
        manager._games.pop(player.game_id, None)

        # should return without error
        await manager.leave_game(conn)

    async def test_handle_game_action_not_in_game_returns_error(self, manager):
        """Performing a game action without joining returns an error."""
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.handle_game_action(conn, GameAction.DISCARD, {})

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NOT_IN_GAME

    async def test_handle_game_action_game_is_none(self, manager):
        """Performing a game action when game is missing from mapping does not raise."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)

        # should return silently without error
        await manager.handle_game_action(conn, GameAction.DISCARD, {})
        assert len(conn.sent_messages) == 0

    async def test_handle_game_action_no_lock_returns_error(self, manager):
        """Performing a game action when the game has no lock (pre-start) returns an error."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=0)

        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        # game exists but hasn't started (no lock)
        game = manager.get_game("game1")
        assert game is not None
        assert "game1" not in manager._game_locks

        await manager.handle_game_action(conn, GameAction.DISCARD, {})
        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.GAME_NOT_STARTED

    async def test_broadcast_chat_game_is_none(self, manager):
        """Broadcasting chat when game is missing from mapping does not raise."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)

        # should return silently without error
        await manager.broadcast_chat(conn, "hello")
        assert len(conn.sent_messages) == 0

    async def test_start_game_failure_rolls_back_started_flag(self, manager):
        """When start_game returns an ErrorEvent, game.started is rolled back."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        # patch start_game to return an error (simulating unsupported settings)
        error_events = [
            ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(
                    code=GameErrorCode.INVALID_ACTION,
                    message="unsupported settings",
                    target="all",
                ),
                target=BroadcastTarget(),
            )
        ]
        manager._game_service.start_game = AsyncMock(return_value=error_events)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        # game.started should be rolled back to False
        game = manager.get_game("game1")
        assert game is not None
        assert game.started is False

        # no lock or heartbeat resources should be allocated
        assert "game1" not in manager._game_locks

        # error should have been broadcast to players
        error_msgs = [m for m in conn1.sent_messages if m.get("type") == EventType.ERROR]
        assert len(error_msgs) == 1
        assert error_msgs[0]["message"] == "unsupported settings"
