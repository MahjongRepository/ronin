import pytest
from mahjong.tile import TilesConverter
from pydantic import ValidationError

from game.logic.enums import GameAction
from game.messaging.encoder import decode, encode
from game.messaging.events import EventType
from game.messaging.router import MessageRouter
from game.messaging.types import (
    ChatMessage,
    ClientMessageType,
    JoinGameMessage,
    PingMessage,
    SessionErrorCode,
    SessionMessageType,
    parse_client_message,
)
from game.session.manager import SessionManager
from game.tests.mocks import MockConnection, MockGameService


class TestParseClientMessage:
    def test_parse_join_game(self):
        data = {"type": ClientMessageType.JOIN_GAME, "game_id": "game1", "player_name": "Alice"}
        msg = parse_client_message(data)
        assert msg.type == ClientMessageType.JOIN_GAME
        assert isinstance(msg, JoinGameMessage)
        assert msg.game_id == "game1"
        assert msg.player_name == "Alice"

    def test_parse_chat(self):
        data = {"type": ClientMessageType.CHAT, "text": "Hello!"}
        msg = parse_client_message(data)
        assert msg.type == ClientMessageType.CHAT
        assert isinstance(msg, ChatMessage)
        assert msg.text == "Hello!"

    def test_parse_ping(self):
        data = {"type": ClientMessageType.PING}
        msg = parse_client_message(data)
        assert msg.type == ClientMessageType.PING
        assert isinstance(msg, PingMessage)

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
                "type": ClientMessageType.JOIN_GAME,
                "game_id": "game1",
                "player_name": "Alice",
            },
        )

        # check the response: game_joined + game_started + round_started events
        assert len(connection.sent_messages) == 3
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.GAME_JOINED
        assert response["game_id"] == "game1"
        assert response["players"] == ["Alice"]
        # second message is game_started (flat, no game_event wrapper)
        game_event = connection.sent_messages[1]
        assert game_event["type"] == EventType.GAME_STARTED
        # third message is round_started for seat_0
        round_event = connection.sent_messages[2]
        assert round_event["type"] == EventType.ROUND_STARTED

    async def test_invalid_message_returns_error(self, setup):
        router, connection, _ = setup

        await router.handle_message(connection, {"type": "bogus"})

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

    async def test_leave_game_message(self, setup):
        """Leave game message calls session_manager.leave_game."""
        router, connection, session_manager = setup
        session_manager.create_game("game1")
        await router.handle_message(
            connection,
            {"type": ClientMessageType.JOIN_GAME, "game_id": "game1", "player_name": "Alice"},
        )
        connection._outbox.clear()

        await router.handle_message(connection, {"type": ClientMessageType.LEAVE_GAME})

        # player should have received game_left
        assert any(m.get("type") == SessionMessageType.GAME_LEFT for m in connection.sent_messages)

    async def test_game_action_routes_to_session_manager(self, setup):
        """Game action message routes through session manager and returns events."""
        router, connection, session_manager = setup
        session_manager.create_game("game1")
        await router.handle_message(
            connection,
            {"type": ClientMessageType.JOIN_GAME, "game_id": "game1", "player_name": "Alice"},
        )
        connection._outbox.clear()

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.GAME_ACTION,
                "action": GameAction.DISCARD,
                "data": {"tile_id": TilesConverter.string_to_136_array(man="1")[0]},
            },
        )

        # mock service returns events as flat messages
        assert len(connection.sent_messages) >= 1

    async def test_game_action_error_returns_action_failed(self, setup):
        """Game action that raises error returns action_failed error."""
        router, connection, session_manager = setup
        session_manager.create_game("game1")
        await router.handle_message(
            connection,
            {"type": ClientMessageType.JOIN_GAME, "game_id": "game1", "player_name": "Alice"},
        )
        connection._outbox.clear()

        # patch handle_game_action to raise ValueError
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

    async def test_ping_responds_with_pong(self, setup):
        """Ping message is handled by the router and responds with pong."""
        router, connection, _ = setup

        await router.handle_message(connection, {"type": ClientMessageType.PING})

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.PONG


class TestMockConnectionProtocol:
    async def test_send_message_encodes_to_msgpack(self):
        connection = MockConnection()
        message = {"type": "test", "value": 42}

        await connection.send_message(message)

        assert len(connection.sent_messages) == 1
        assert connection.sent_messages[0] == message

    async def test_receive_message_decodes_from_msgpack(self):
        connection = MockConnection()
        message = {"type": "test", "value": 42}
        await connection.simulate_receive(message)

        received = await connection.receive_message()

        assert received == message

    async def test_send_bytes_stores_decoded_message(self):
        connection = MockConnection()
        message = {"type": "test", "data": [1, 2, 3]}
        encoded = encode(message)

        await connection.send_bytes(encoded)

        assert connection.sent_messages[0] == message

    async def test_receive_bytes_returns_encoded_data(self):
        connection = MockConnection()
        message = {"type": "test", "nested": {"key": "value"}}
        await connection.simulate_receive(message)

        raw_bytes = await connection.receive_bytes()

        assert decode(raw_bytes) == message

    async def test_closed_connection_raises_on_send(self):
        connection = MockConnection()
        await connection.close()

        with pytest.raises(RuntimeError, match="Connection is closed"):
            await connection.send_message({"type": "test"})

    async def test_closed_connection_raises_on_receive(self):
        connection = MockConnection()
        await connection.close()

        with pytest.raises(RuntimeError, match="Connection is closed"):
            await connection.receive_message()

    def test_is_closed_property_default_false(self):
        """MockConnection starts as not closed."""
        connection = MockConnection()

        assert connection.is_closed is False

    async def test_is_closed_property_true_after_close(self):
        """MockConnection is_closed returns True after close."""
        connection = MockConnection()
        await connection.close()

        assert connection.is_closed is True

    async def test_simulate_receive_nowait(self):
        """simulate_receive_nowait queues message without awaiting."""
        connection = MockConnection()
        connection.simulate_receive_nowait({"type": "test", "value": 42})

        received = await connection.receive_message()

        assert received == {"type": "test", "value": 42}


class TestMockGameServiceGetPlayerSeat:
    def test_get_player_seat_unknown_game_returns_none(self):
        """Return None when game_id is not found."""
        service = MockGameService()

        result = service.get_player_seat("nonexistent_game", "Alice")

        assert result is None


class TestMockGameServiceBotReplacement:
    """Tests for bot replacement stub methods."""

    def test_replace_player_with_bot_does_nothing(self):
        service = MockGameService()
        service.replace_player_with_bot("game1", "Alice")

    async def test_process_bot_actions_after_replacement_returns_empty(self):
        service = MockGameService()
        result = await service.process_bot_actions_after_replacement("game1", seat=0)
        assert result == []
