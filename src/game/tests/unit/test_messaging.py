import pytest
from mahjong.tile import TilesConverter
from pydantic import ValidationError

from game.logic.enums import GameAction
from game.messaging.router import MessageRouter
from game.messaging.types import (
    ClientMessageType,
    GameJoinedMessage,
    JoinGameMessage,
    SessionErrorCode,
    SessionMessageType,
    parse_client_message,
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
            {
                "type": ClientMessageType.JOIN_GAME,
                "game_id": "game1",
                "player_name": "Alice",
                "session_token": "tok-test",
            },
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
            {
                "type": ClientMessageType.JOIN_GAME,
                "game_id": "game1",
                "player_name": "Alice",
                "session_token": "tok-test",
            },
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
            {
                "type": ClientMessageType.JOIN_GAME,
                "game_id": "game1",
                "player_name": "Alice",
                "session_token": "tok-test",
            },
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


class TestJoinGameMessageSessionToken:
    """Validate session_token field on JoinGameMessage."""

    def test_join_game_rejects_missing_session_token(self):
        with pytest.raises(ValidationError):
            JoinGameMessage(game_id="abc", player_name="Alice")  # type: ignore[call-arg]

    def test_join_game_with_valid_session_token(self):
        token = "a1b2c3d4-e5f6"
        msg = JoinGameMessage(game_id="abc", player_name="Alice", session_token=token)
        assert msg.session_token == token

    def test_join_game_rejects_invalid_session_token_characters(self):
        with pytest.raises(ValidationError):
            JoinGameMessage(game_id="abc", player_name="Alice", session_token="bad token!")

    def test_join_game_rejects_too_long_session_token(self):
        with pytest.raises(ValidationError):
            JoinGameMessage(game_id="abc", player_name="Alice", session_token="x" * 51)

    def test_parse_join_game_with_session_token(self):
        data = {
            "type": "join_game",
            "game_id": "game1",
            "player_name": "Alice",
            "session_token": "abc-123",
        }
        msg = parse_client_message(data)
        assert isinstance(msg, JoinGameMessage)
        assert msg.session_token == "abc-123"

    def test_parse_join_game_rejects_missing_session_token(self):
        data = {
            "type": "join_game",
            "game_id": "game1",
            "player_name": "Alice",
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestGameJoinedMessageSessionToken:
    """Validate session_token field on GameJoinedMessage."""

    def test_game_joined_requires_session_token(self):
        with pytest.raises(ValidationError):
            GameJoinedMessage.model_validate({"game_id": "abc", "players": ["Alice"]})

    def test_game_joined_includes_session_token_in_dump(self):
        msg = GameJoinedMessage(game_id="abc", players=["Alice"], session_token="tok-123")
        dumped = msg.model_dump()
        assert dumped["session_token"] == "tok-123"
        assert dumped["game_id"] == "abc"
        assert dumped["players"] == ["Alice"]


class TestRouterPassesSessionToken:
    """Verify the router forwards session_token from JoinGameMessage to SessionManager."""

    @pytest.fixture
    async def setup(self):
        game_service = MockGameService()
        session_manager = SessionManager(game_service)
        router = MessageRouter(session_manager)
        connection = MockConnection()
        await router.handle_connect(connection)
        session_manager.create_game("game1")
        return router, connection, session_manager

    async def test_join_game_with_session_token_passes_through(self, setup):
        router, connection, _ = setup

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.JOIN_GAME,
                "game_id": "game1",
                "player_name": "Alice",
                "session_token": "client-token-123",
            },
        )

        assert any(m.get("type") == SessionMessageType.GAME_JOINED for m in connection.sent_messages)

    async def test_join_game_without_session_token_rejected(self, setup):
        router, connection, _ = setup

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.JOIN_GAME,
                "game_id": "game1",
                "player_name": "Alice",
            },
        )

        assert any(m.get("code") == SessionErrorCode.INVALID_MESSAGE for m in connection.sent_messages)
