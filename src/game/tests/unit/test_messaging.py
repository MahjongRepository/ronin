import pytest
from mahjong.tile import TilesConverter
from pydantic import ValidationError

from game.logic.enums import GameAction, KanType
from game.messaging.router import MessageRouter
from game.messaging.types import (
    ChiMessage,
    ClientMessageType,
    DiscardMessage,
    KanMessage,
    NoDataActionMessage,
    PonMessage,
    RiichiMessage,
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

    async def test_game_action_error_returns_action_failed(self, setup):
        """ValueError/KeyError/TypeError during game action returns ACTION_FAILED error."""
        router, connection, session_manager = setup
        await _setup_player_in_game(session_manager, connection)

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
            connection: object,  # noqa: ARG001
            action: object,  # noqa: ARG001
            data: object,  # noqa: ARG001
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
    """Validate parse_client_message for room-based message types."""

    def test_parse_join_room(self):
        data = {
            "type": "join_room",
            "room_id": "room1",
            "player_name": "Alice",
            "session_token": "tok-alice",
        }
        msg = parse_client_message(data)
        assert msg.type == ClientMessageType.JOIN_ROOM
        assert msg.room_id == "room1"

    def test_parse_set_ready(self):
        data = {"type": "set_ready", "ready": True}
        msg = parse_client_message(data)
        assert msg.type == ClientMessageType.SET_READY
        assert msg.ready is True

    def test_parse_invalid_type_rejected(self):
        data = {"type": "join_game", "game_id": "game1", "player_name": "Alice", "session_token": "tok"}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_discard_message(self):
        data = {"type": "game_action", "action": "discard", "tile_id": 42}
        msg = parse_client_message(data)
        assert isinstance(msg, DiscardMessage)
        assert msg.tile_id == 42

    def test_parse_riichi_message(self):
        data = {"type": "game_action", "action": "declare_riichi", "tile_id": 10}
        msg = parse_client_message(data)
        assert isinstance(msg, RiichiMessage)
        assert msg.tile_id == 10

    def test_parse_pon_message(self):
        data = {"type": "game_action", "action": "call_pon", "tile_id": 5}
        msg = parse_client_message(data)
        assert isinstance(msg, PonMessage)
        assert msg.tile_id == 5

    def test_parse_chi_message(self):
        data = {"type": "game_action", "action": "call_chi", "tile_id": 40, "sequence_tiles": [41, 42]}
        msg = parse_client_message(data)
        assert isinstance(msg, ChiMessage)
        assert msg.tile_id == 40
        assert msg.sequence_tiles == (41, 42)

    def test_parse_kan_message_default_type(self):
        data = {"type": "game_action", "action": "call_kan", "tile_id": 8}
        msg = parse_client_message(data)
        assert isinstance(msg, KanMessage)
        assert msg.tile_id == 8
        assert msg.kan_type == KanType.OPEN

    def test_parse_kan_message_with_type(self):
        data = {"type": "game_action", "action": "call_kan", "tile_id": 8, "kan_type": "closed"}
        msg = parse_client_message(data)
        assert isinstance(msg, KanMessage)
        assert msg.kan_type == KanType.CLOSED

    def test_parse_no_data_action(self):
        data = {"type": "game_action", "action": "pass"}
        msg = parse_client_message(data)
        assert isinstance(msg, NoDataActionMessage)
        assert msg.action == GameAction.PASS

    def test_parse_confirm_round(self):
        data = {"type": "game_action", "action": "confirm_round"}
        msg = parse_client_message(data)
        assert isinstance(msg, NoDataActionMessage)
        assert msg.action == GameAction.CONFIRM_ROUND

    def test_parse_game_action_missing_required_field(self):
        data = {"type": "game_action", "action": "discard"}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_game_action_invalid_action(self):
        data = {"type": "game_action", "action": "invalid_action"}
        with pytest.raises(ValidationError):
            parse_client_message(data)
