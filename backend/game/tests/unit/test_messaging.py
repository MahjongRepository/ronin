import pytest
from mahjong.tile import TilesConverter
from pydantic import ValidationError

from game.logic.enums import GameAction
from game.logic.exceptions import InvalidDiscardError
from game.messaging.router import MessageRouter
from game.messaging.types import (
    ChiMessage,
    ClientMessageType,
    DiscardMessage,
    ReconnectMessage,
    SessionErrorCode,
    SessionMessageType,
    parse_client_message,
)
from game.session.manager import SessionManager
from game.tests.mocks import MockConnection, MockGameService


async def _setup_player_in_game(session_manager, connection):
    """Put a player into a started game via the room flow."""
    session_manager.create_room("game1", num_ai_players=3)
    await session_manager.join_room(connection, "game1", "Alice", "tok-alice")
    await session_manager.set_ready(connection, ready=True)
    connection._outbox.clear()


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

    async def test_reconnect_routes_to_session_manager(self, setup):
        """Reconnect message dispatches through router to session_manager.reconnect."""
        router, connection, _ = setup

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.RECONNECT,
                "room_id": "game1",
                "session_token": "tok-abc",
            },
        )

        # no session exists, so we get an error back
        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.RECONNECT_NO_SESSION

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

    async def test_ping_routes_to_session_manager(self, setup):
        """Ping message dispatches through router to session_manager.handle_ping."""
        router, connection, _ = setup

        await router.handle_message(connection, {"type": ClientMessageType.PING})

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.PONG

    async def test_game_rule_error_returns_action_failed(self, setup):
        """GameRuleError during game action returns ACTION_FAILED error."""
        router, connection, session_manager = setup
        await _setup_player_in_game(session_manager, connection)

        async def raise_game_rule_error(
            connection: object,
            action: object,
            data: object,
        ) -> None:
            raise InvalidDiscardError("tile not in hand")

        session_manager.handle_game_action = raise_game_rule_error

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.GAME_ACTION,
                "action": GameAction.DISCARD,
                "tile_id": 0,
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.ACTION_FAILED
        assert response["message"] == "tile not in hand"

    async def test_key_error_returns_action_failed(self, setup):
        """KeyError during game action returns ACTION_FAILED error (handled gracefully)."""
        router, connection, session_manager = setup
        await _setup_player_in_game(session_manager, connection)

        async def raise_key_error(
            connection: object,
            action: object,
            data: object,
        ) -> None:
            raise KeyError("missing key")

        session_manager.handle_game_action = raise_key_error

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.GAME_ACTION,
                "action": GameAction.DISCARD,
                "tile_id": 0,
            },
        )

        assert not connection.is_closed
        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.ACTION_FAILED

    async def test_game_action_error_returns_action_failed(self, setup):
        """ValueError during game action returns ACTION_FAILED error."""
        router, connection, session_manager = setup
        await _setup_player_in_game(session_manager, connection)

        async def raise_value_error(
            connection: object,
            action: object,
            data: object,
        ) -> None:
            raise ValueError("invalid tile")

        session_manager.handle_game_action = raise_value_error

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.GAME_ACTION,
                "action": GameAction.DISCARD,
                "tile_id": TilesConverter.string_to_136_array(man="1")[0],
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
        await _setup_player_in_game(session_manager, connection)

        async def raise_runtime_error(
            connection: object,
            action: object,
            data: object,
        ) -> None:
            raise RuntimeError("unexpected crash")

        session_manager.handle_game_action = raise_runtime_error

        await router.handle_message(
            connection,
            {
                "type": ClientMessageType.GAME_ACTION,
                "action": GameAction.DISCARD,
                "tile_id": 0,
            },
        )

        assert connection.is_closed


class TestParseClientMessage:
    """Validate parse_client_message error handling and non-trivial parsing."""

    def test_parse_invalid_type_rejected(self):
        data = {"type": "join_game", "game_id": "game1", "player_name": "Alice", "session_token": "tok"}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_chi_coerces_sequence_tiles_to_tuple(self):
        data = {"type": "game_action", "action": "call_chi", "tile_id": 40, "sequence_tiles": [41, 42]}
        msg = parse_client_message(data)
        assert isinstance(msg, ChiMessage)
        assert msg.sequence_tiles == (41, 42)

    def test_parse_kan_message_requires_kan_type(self):
        data = {"type": "game_action", "action": "call_kan", "tile_id": 8}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_game_action_missing_required_field(self):
        data = {"type": "game_action", "action": "discard"}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_game_action_invalid_action(self):
        data = {"type": "game_action", "action": "invalid_action"}
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestReconnectMessageParsing:
    """Validate ReconnectMessage parsing and field validation."""

    def test_parse_reconnect_message(self):
        data = {
            "type": "reconnect",
            "room_id": "game1",
            "session_token": "tok-abc_123",
        }
        msg = parse_client_message(data)
        assert isinstance(msg, ReconnectMessage)
        assert msg.room_id == "game1"
        assert msg.session_token == "tok-abc_123"

    def test_reconnect_missing_session_token_rejected(self):
        data = {"type": "reconnect", "room_id": "game1"}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_reconnect_missing_room_id_rejected(self):
        data = {"type": "reconnect", "session_token": "tok-abc"}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_reconnect_invalid_session_token_pattern_rejected(self):
        data = {
            "type": "reconnect",
            "room_id": "game1",
            "session_token": "tok with spaces!",
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_reconnect_invalid_room_id_pattern_rejected(self):
        data = {
            "type": "reconnect",
            "room_id": "room with spaces!",
            "session_token": "tok-abc",
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestInputValidation:
    """Boundary validation for wire message fields."""

    def test_tile_id_negative_rejected(self):
        data = {"type": "game_action", "action": "discard", "tile_id": -1}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_tile_id_too_large_rejected(self):
        data = {"type": "game_action", "action": "discard", "tile_id": 136}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_tile_id_max_valid(self):
        data = {"type": "game_action", "action": "discard", "tile_id": 135}
        msg = parse_client_message(data)
        assert isinstance(msg, DiscardMessage)
        assert msg.tile_id == 135

    def test_chi_sequence_tile_out_of_range_rejected(self):
        data = {"type": "game_action", "action": "call_chi", "tile_id": 0, "sequence_tiles": [4, 200]}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_player_name_whitespace_only_rejected(self):
        data = {
            "type": "join_room",
            "room_id": "room1",
            "player_name": "   ",
            "session_token": "tok-abc",
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_session_token_special_chars_rejected(self):
        data = {
            "type": "join_room",
            "room_id": "room1",
            "player_name": "Alice",
            "session_token": "tok with spaces!",
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_session_token_valid_pattern(self):
        data = {
            "type": "join_room",
            "room_id": "room1",
            "player_name": "Alice",
            "session_token": "tok-abc_123",
        }
        msg = parse_client_message(data)
        assert msg.session_token == "tok-abc_123"

    def test_player_name_with_tabs_rejected(self):
        data = {
            "type": "join_room",
            "room_id": "room1",
            "player_name": "Ali\tce",
            "session_token": "tok-abc",
        }
        with pytest.raises(ValidationError, match="control characters"):
            parse_client_message(data)

    def test_player_name_with_newlines_rejected(self):
        data = {
            "type": "join_room",
            "room_id": "room1",
            "player_name": "Ali\nce",
            "session_token": "tok-abc",
        }
        with pytest.raises(ValidationError, match="control characters"):
            parse_client_message(data)

    def test_player_name_stripped(self):
        data = {
            "type": "join_room",
            "room_id": "room1",
            "player_name": "  Alice  ",
            "session_token": "tok-abc",
        }
        msg = parse_client_message(data)
        assert msg.player_name == "Alice"

    def test_chat_text_with_null_byte_rejected(self):
        data = {
            "type": "chat",
            "text": "hello\x00world",
        }
        with pytest.raises(ValidationError, match="control characters"):
            parse_client_message(data)

    def test_chat_text_with_escape_rejected(self):
        data = {
            "type": "chat",
            "text": "hello\x1bworld",
        }
        with pytest.raises(ValidationError, match="control characters"):
            parse_client_message(data)

    def test_chat_text_allows_common_whitespace(self):
        data = {
            "type": "chat",
            "text": "hello\tworld\nfoo",
        }
        msg = parse_client_message(data)
        assert msg.text == "hello\tworld\nfoo"

    def test_chat_text_valid(self):
        data = {
            "type": "chat",
            "text": "hello world!",
        }
        msg = parse_client_message(data)
        assert msg.text == "hello world!"

    def test_player_name_with_ansi_escape_rejected(self):
        data = {
            "type": "join_room",
            "room_id": "room1",
            "player_name": "Ali\x1b[31mce",
            "session_token": "tok-abc",
        }
        with pytest.raises(ValidationError, match="control characters"):
            parse_client_message(data)
