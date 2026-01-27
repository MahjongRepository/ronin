import pytest
from pydantic import ValidationError

from game.logic.mock import MockGameService
from game.messaging.mock import MockConnection
from game.messaging.router import MessageRouter
from game.messaging.types import (
    ClientMessageType,
    ServerMessageType,
    parse_client_message,
)
from game.session.manager import SessionManager


class TestParseClientMessage:
    def test_parse_join_game(self):
        data = {"type": "join_game", "game_id": "game1", "player_name": "Alice"}
        msg = parse_client_message(data)
        assert msg.type == ClientMessageType.JOIN_GAME
        assert msg.game_id == "game1"
        assert msg.player_name == "Alice"

    def test_parse_chat(self):
        data = {"type": "chat", "text": "Hello!"}
        msg = parse_client_message(data)
        assert msg.type == ClientMessageType.CHAT
        assert msg.text == "Hello!"

    def test_parse_invalid_type(self):
        data = {"type": "invalid_type"}
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestMessageRouter:
    @pytest.fixture
    async def setup(self):
        game_service = MockGameService()
        session_manager = SessionManager(game_service)
        router = MessageRouter(session_manager)
        connection = MockConnection()
        await router.handle_connect(connection)
        return router, connection, session_manager

    async def test_join_game(self, setup):
        router, connection, session_manager = setup
        session_manager.create_game("game1")

        await router.handle_message(
            connection,
            {
                "type": "join_game",
                "game_id": "game1",
                "player_name": "Alice",
            },
        )

        # check the response
        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == ServerMessageType.GAME_JOINED
        assert response["game_id"] == "game1"
        assert response["players"] == ["Alice"]

    async def test_invalid_message_returns_error(self, setup):
        router, connection, _ = setup

        await router.handle_message(connection, {"type": "bogus"})

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == ServerMessageType.ERROR
        assert response["code"] == "invalid_message"

    async def test_chat_requires_game(self, setup):
        router, connection, _ = setup

        await router.handle_message(
            connection,
            {
                "type": "chat",
                "text": "Hello!",
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == ServerMessageType.ERROR
        assert response["code"] == "not_in_game"
