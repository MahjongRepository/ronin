from unittest.mock import AsyncMock

from game.logic.enums import GameAction, GameErrorCode
from game.logic.events import BroadcastTarget, ErrorEvent, EventType, ServiceEvent
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.tests.mocks import MockConnection

from .helpers import create_started_game


class TestSessionManagerDefensiveChecks:
    """Tests for defensive checks that guard against invalid state."""

    async def test_handle_game_action_not_in_game_returns_error(self, manager):
        """Performing a game action without joining returns an error."""
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.handle_game_action(conn, GameAction.DISCARD, {})

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NOT_IN_GAME

    async def test_leave_game_when_game_is_none(self, manager):
        """Leaving when the game mapping is missing clears player state and does not raise."""
        conns = await create_started_game(manager, "game1")

        player = manager._players[conns[0].connection_id]

        # remove the game from the internal mapping to simulate the defensive case
        manager._games.pop(player.game_id, None)

        # should return without error and clear player game association
        await manager.leave_game(conns[0])
        assert player.game_id is None
        assert player.seat is None

    async def test_handle_game_action_game_is_none(self, manager):
        """Performing a game action when game is missing from mapping does not raise."""
        conns = await create_started_game(manager, "game1")
        conns[0]._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)

        # should return silently without error
        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})
        assert len(conns[0].sent_messages) == 0

    async def test_handle_game_action_no_lock_returns_error(self, manager):
        """Performing a game action when the game has no lock (edge case) returns an error."""
        conns = await create_started_game(manager, "game1")
        conns[0]._outbox.clear()

        # remove lock to simulate edge case
        manager._game_locks.pop("game1", None)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})
        assert len(conns[0].sent_messages) == 1
        msg = conns[0].sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.GAME_NOT_STARTED

    async def test_broadcast_chat_game_is_none(self, manager):
        """Broadcasting chat when game is missing from mapping does not raise."""
        conns = await create_started_game(manager, "game1")
        conns[0]._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)

        # should return silently without error
        await manager.broadcast_chat(conns[0], "hello")
        assert len(conns[0].sent_messages) == 0

    async def test_start_game_failure_rolls_back_started_flag(self, manager):
        """When start_game returns an ErrorEvent, game.started is rolled back."""
        manager.create_room("game1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "game1", "Alice", "tok-alice")
        await manager.join_room(conn2, "game1", "Bob", "tok-bob")

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

        await manager.set_ready(conn1, ready=True)
        await manager.set_ready(conn2, ready=True)

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

    async def test_leave_pre_start_game_removes_session(self, manager):
        """Leaving a game that hasn't started (e.g. start failure) removes the session."""
        manager.create_room("game1", num_ai_players=2)
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)

        await manager.join_room(conn1, "game1", "Alice", "tok-alice")
        await manager.join_room(conn2, "game1", "Bob", "tok-bob")

        # patch start_game to return an error (game.started rolled back to False)
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

        await manager.set_ready(conn1, ready=True)
        await manager.set_ready(conn2, ready=True)

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is False

        player = manager._players[conn1.connection_id]
        token = player.session_token

        # leave_game on a non-started game should remove the session entirely
        await manager.leave_game(conn1)

        assert player.game_id is None
        assert player.seat is None
        assert manager._session_store._sessions.get(token) is None
