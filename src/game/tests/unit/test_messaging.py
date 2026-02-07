import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import GameAction
from game.messaging.router import MessageRouter
from game.messaging.types import (
    ClientMessageType,
    SessionErrorCode,
    SessionMessageType,
)
from game.session.manager import SessionManager
from game.tests.mocks import MockConnection, MockGameService


class TestMessageRouterBranches:
    """Router dispatch branches and error paths not covered by websocket integration tests."""

    @pytest.fixture
    async def setup(self):
        game_service = MockGameService()
        session_manager = SessionManager(game_service)
        router = MessageRouter(session_manager)
        connection = MockConnection()
        await router.handle_connect(connection)
        return router, connection, session_manager

    async def test_disconnect_without_joining_game(self, setup):
        """Disconnecting a registered connection that never joined a game returns cleanly."""
        router, connection, _ = setup

        await router.handle_disconnect(connection)

        assert len(connection.sent_messages) == 0

    async def test_invalid_message_returns_error(self, setup):
        router, connection, _ = setup

        await router.handle_message(connection, {"type": "invalid"})

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.INVALID_MESSAGE

    async def test_chat_requires_game(self, setup):
        router, connection, _ = setup

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.CHAT,
                "text": "Hello!",
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.NOT_IN_GAME

    async def test_leave_game_routes_to_session_manager(self, setup):
        """Leave game message dispatches through router to session_manager.leave_game."""
        router, connection, session_manager = setup
        session_manager.create_game("game1")
        await router.handle_message(
            connection,
            {"type": ClientMessageType.JOIN_GAME, "game_id": "game1", "player_name": "Alice"},
        )
        connection._outbox.clear()

        await router.handle_message(connection, {"type": ClientMessageType.LEAVE_GAME})

        assert any(m.get("type") == SessionMessageType.GAME_LEFT for m in connection.sent_messages)

    async def test_ping_routes_to_session_manager(self, setup):
        """Ping message dispatches through router to session_manager.handle_ping."""
        router, connection, _ = setup

        await router.handle_message(connection, {"type": ClientMessageType.PING})

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.PONG

    async def test_game_action_error_returns_action_failed(self, setup):
        """ValueError/KeyError/TypeError during game action returns ACTION_FAILED error."""
        router, connection, session_manager = setup
        session_manager.create_game("game1")
        await router.handle_message(
            connection,
            {"type": ClientMessageType.JOIN_GAME, "game_id": "game1", "player_name": "Alice"},
        )
        connection._outbox.clear()

        async def raise_value_error(
            connection: object,  # noqa: ARG001
            action: object,  # noqa: ARG001
            data: object,  # noqa: ARG001
        ) -> None:
            raise ValueError("invalid tile")

        session_manager.handle_game_action = raise_value_error

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.GAME_ACTION,
                "action": GameAction.DISCARD,
                "data": {"tile_id": TilesConverter.string_to_136_array(man="1")[0]},
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.ACTION_FAILED
        assert response["message"] == "invalid tile"

    async def test_unexpected_exception_triggers_close_game_on_error(self, setup):
        """Fatal exception during game action triggers close_game_on_error."""
        router, connection, session_manager = setup
        session_manager.create_game("game1")
        await router.handle_message(
            connection,
            {"type": ClientMessageType.JOIN_GAME, "game_id": "game1", "player_name": "Alice"},
        )
        connection._outbox.clear()

        async def raise_runtime_error(
            connection: object,  # noqa: ARG001
            action: object,  # noqa: ARG001
            data: object,  # noqa: ARG001
        ) -> None:
            raise RuntimeError("unexpected crash")

        session_manager.handle_game_action = raise_runtime_error  # type: ignore[assignment]

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.GAME_ACTION,
                "action": GameAction.DISCARD,
                "data": {"tile_id": 0},
            },
        )

        assert connection.is_closed
