import pytest

from game.logic.exceptions import InvalidDiscardError
from game.messaging.types import (
    SessionErrorCode,
    SessionMessageType,
)
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.session.manager import SessionManager
from game.session.models import PlayerSpec
from game.tests.helpers.auth import TEST_TICKET_SECRET, make_test_game_ticket
from game.tests.mocks import MockConnection, MockGameService


async def _setup_player_in_game(session_manager, connection):
    ticket = make_test_game_ticket("Alice", "game1", user_id="user-0")
    specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
    session_manager.create_pending_game("game1", specs, num_ai_players=3)
    await session_manager.join_game(connection, "game1", ticket)
    connection._outbox.clear()


class TestMessageRouterBranches:
    @pytest.fixture
    async def setup(self):
        game_service = MockGameService()
        session_manager = SessionManager(game_service)
        router = MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)
        connection = MockConnection()
        await router.handle_connect(connection)
        return router, connection, session_manager

    async def test_message_router__when_reconnect_without_session__should_return_no_session_error(self, setup):
        router, connection, _ = setup

        ticket = make_test_game_ticket("Alice", "test-game")
        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.RECONNECT,
                "game_ticket": ticket,
            },
        )

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.RECONNECT_NO_SESSION

    async def test_message_router__when_reconnect_ticket_invalid__should_return_invalid_ticket_error(self, setup):
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

    async def test_message_router__when_join_ticket_game_id_mismatches__should_return_invalid_ticket_error(self, setup):
        router, connection, session_manager = setup
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

    async def test_message_router__when_disconnect_without_joining_game__should_send_nothing(self, setup):
        router, connection, _ = setup

        await router.handle_disconnect(connection)

        assert len(connection.sent_messages) == 0

    async def test_message_router__when_message_invalid__should_return_invalid_message_error(self, setup):
        router, connection, _ = setup

        await router.handle_message(connection, {"t": "invalid"})

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.INVALID_MESSAGE

    async def test_message_router__when_chat_without_game__should_return_not_in_game_error(self, setup):
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

    async def test_message_router__when_ping__should_reply_pong(self, setup):
        router, connection, _ = setup

        await router.handle_message(connection, {"t": WireClientMessageType.PING})

        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.PONG

    async def test_message_router__when_game_rule_error_raised__should_return_action_failed_error(self, setup):
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

    async def test_message_router__when_unexpected_exception_raised__should_close_connection(self, setup):
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
