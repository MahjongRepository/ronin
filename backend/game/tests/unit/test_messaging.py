import pytest
from pydantic import ValidationError

from game.logic.exceptions import InvalidDiscardError
from game.messaging.router import MessageRouter
from game.messaging.types import (
    ChiMessage,
    DiscardMessage,
    ReconnectMessage,
    SessionErrorCode,
    SessionMessageType,
    parse_client_message,
)
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.types import PlayerSpec
from game.session.manager import SessionManager
from game.tests.helpers.auth import TEST_TICKET_SECRET, make_test_game_ticket
from game.tests.mocks import MockConnection, MockGameService


async def _setup_player_in_game(session_manager, connection):
    """Put a player into a started game via the pending game flow."""
    ticket = make_test_game_ticket("Alice", "game1", user_id="user-0")
    specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
    session_manager.create_pending_game("game1", specs, num_ai_players=3)
    await session_manager.join_game(connection, "game1", ticket)
    connection._outbox.clear()


class TestMessageRouterBranches:
    """Router dispatch branches and error paths not covered by websocket integration tests."""

    @pytest.fixture
    async def setup(self):
        game_service = MockGameService()
        session_manager = SessionManager(game_service)
        router = MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)
        connection = MockConnection()
        await router.handle_connect(connection)
        return router, connection, session_manager

    async def test_reconnect_routes_to_session_manager(self, setup):
        """Reconnect message with valid ticket dispatches through router to session_manager.reconnect."""
        router, connection, _ = setup

        ticket = make_test_game_ticket("Alice", "test-game")
        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.RECONNECT,
                "game_ticket": ticket,
            },
        )

        # no session exists, so we get an error back
        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.RECONNECT_NO_SESSION

    async def test_reconnect_invalid_ticket_rejected(self, setup):
        """Reconnect with invalid ticket returns INVALID_TICKET error."""
        router, connection, _ = setup

        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.RECONNECT,
                "game_ticket": "invalid-ticket-string",
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.INVALID_TICKET

    async def test_join_game_with_ticket_game_id_mismatch(self, setup):
        """JOIN_GAME with ticket signed for a different game returns INVALID_TICKET."""
        router, connection, session_manager = setup
        # Ticket is signed for "other-game" but connection.game_id is "test-game"
        ticket = make_test_game_ticket("Alice", "other-game")

        specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
        session_manager.create_pending_game("test-game", specs, num_ai_players=3)

        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.JOIN_GAME,
                "game_ticket": ticket,
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.INVALID_TICKET
        assert "mismatch" in response["message"]

    async def test_disconnect_without_joining_game(self, setup):
        """Disconnecting a registered connection that never joined a game returns cleanly."""
        router, connection, _ = setup

        await router.handle_disconnect(connection)

        assert len(connection.sent_messages) == 0

    async def test_invalid_message_returns_error(self, setup):
        router, connection, _ = setup

        await router.handle_message(connection, {"t": "invalid"})

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.INVALID_MESSAGE

    async def test_chat_requires_game(self, setup):
        router, connection, _ = setup

        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.CHAT,
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

        await router.handle_message(connection, {"t": WireClientMessageType.PING})

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
                "t": WireClientMessageType.GAME_ACTION,
                "a": WireGameAction.DISCARD,
                "ti": 0,
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.ACTION_FAILED
        assert response["message"] == "tile not in hand"

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
                "t": WireClientMessageType.GAME_ACTION,
                "a": WireGameAction.DISCARD,
                "ti": 0,
            },
        )

        assert connection.is_closed


class TestParseClientMessage:
    """Validate parse_client_message error handling and non-trivial parsing."""

    def test_parse_invalid_type_rejected(self):
        data = {"t": 99, "game_ticket": "some-ticket"}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_chi_coerces_sequence_tiles_to_tuple(self):
        data = {
            "t": WireClientMessageType.GAME_ACTION,
            "a": WireGameAction.CALL_CHI,
            "ti": 40,
            "sequence_tiles": [41, 42],
        }
        msg = parse_client_message(data)
        assert isinstance(msg, ChiMessage)
        assert msg.sequence_tiles == (41, 42)

    def test_parse_kan_message_requires_kan_type(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.CALL_KAN, "ti": 8}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_game_action_missing_required_field(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_game_action_invalid_action(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": 99}
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestReconnectMessageParsing:
    """Validate ReconnectMessage parsing and field validation."""

    def test_parse_reconnect_message(self):
        data = {
            "t": WireClientMessageType.RECONNECT,
            "game_ticket": "some-ticket-string",
        }
        msg = parse_client_message(data)
        assert isinstance(msg, ReconnectMessage)
        assert msg.game_ticket == "some-ticket-string"

    def test_reconnect_missing_game_ticket_rejected(self):
        data = {"t": WireClientMessageType.RECONNECT}
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestInputValidation:
    """Boundary validation for wire message fields."""

    def test_tile_id_negative_rejected(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": -1}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_tile_id_too_large_rejected(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": 136}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_tile_id_max_valid(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": 135}
        msg = parse_client_message(data)
        assert isinstance(msg, DiscardMessage)
        assert msg.tile_id == 135

    def test_chi_sequence_tile_out_of_range_rejected(self):
        data = {
            "t": WireClientMessageType.GAME_ACTION,
            "a": WireGameAction.CALL_CHI,
            "ti": 0,
            "sequence_tiles": [4, 200],
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_join_game_missing_game_ticket_rejected(self):
        data = {
            "t": WireClientMessageType.JOIN_GAME,
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_join_game_empty_game_ticket_rejected(self):
        data = {
            "t": WireClientMessageType.JOIN_GAME,
            "game_ticket": "",
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_chat_text_with_null_byte_rejected(self):
        data = {
            "t": WireClientMessageType.CHAT,
            "text": "hello\x00world",
        }
        with pytest.raises(ValidationError, match="control characters"):
            parse_client_message(data)

    def test_chat_text_allows_common_whitespace(self):
        data = {
            "t": WireClientMessageType.CHAT,
            "text": "hello\tworld\nfoo",
        }
        msg = parse_client_message(data)
        assert msg.text == "hello\tworld\nfoo"
