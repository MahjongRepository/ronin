import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

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
from game.tests.unit.session.helpers import create_started_game, wait_for_background_tasks


async def _setup_player_in_game(session_manager, connection):
    ticket = make_test_game_ticket(username="Alice", room_id="game1", user_id="user-0")
    specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
    session_manager.create_pending_game(game_id="game1", player_specs=specs, num_ai_players=3)
    await session_manager.join_game(connection, game_id="game1", session_token=ticket)
    connection._outbox.clear()


class TestMessageRouterBranches:
    @pytest.fixture
    async def setup(self):
        game_service = MockGameService()
        session_manager = SessionManager(game_service)
        router = MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)
        connection = MockConnection()
        router.handle_connect(connection)
        return router, connection, session_manager

    async def test_message_router__when_reconnect_without_session__should_return_no_session_error(self, setup):
        router, connection, _ = setup

        ticket = make_test_game_ticket(username="Alice", room_id="test-game")
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
        ticket = make_test_game_ticket(username="Alice", room_id="other-game")

        specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
        session_manager.create_pending_game(game_id="test-game", player_specs=specs, num_ai_players=3)

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

    async def test_message_router__when_game_action_raises__should_fail_the_players_game(self, setup):
        router, connection, session_manager = setup
        await _setup_player_in_game(session_manager, connection)
        session_manager.handle_game_action = AsyncMock(side_effect=ValueError("engine state broke"))

        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.GAME_ACTION,
                "a": WireGameAction.DISCARD,
                "ti": 0,
            },
        )
        await wait_for_background_tasks(session_manager)
        assert session_manager.get_game("game1") is None
        assert [m["code"] for m in connection.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
        assert connection._close_code == 1011

    async def test_message_router__when_own_socket_dies_during_an_action__should_propagate_it_as_a_disconnect(
        self, setup
    ):
        router, connection, session_manager = setup
        await _setup_player_in_game(session_manager, connection)
        session_manager.handle_game_action = AsyncMock(side_effect=ConnectionError("socket gone"))

        with pytest.raises(ConnectionError):
            await router.handle_message(
                connection, {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": 0}
            )
        assert session_manager.get_game("game1") is not None

    async def test_message_router__when_join_raises_outside_any_game__should_log_and_close_with_1011(
        self, setup, caplog
    ):
        router, connection, session_manager = setup
        session_manager.join_game = AsyncMock(side_effect=KeyError("session store broke"))
        ticket = make_test_game_ticket(username="Alice", room_id=connection.game_id)

        with caplog.at_level(logging.ERROR):
            await router.handle_message(connection, {"t": WireClientMessageType.JOIN_GAME, "game_ticket": ticket})
        assert [r.msg["event"] for r in caplog.records if r.levelno == logging.ERROR] == [
            "connection failed outside a game"
        ]
        assert [m["code"] for m in connection.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
        assert connection._close_code == 1011


class TestMessageRouterEntryPointFailures:
    async def test_message_router__when_the_final_join_starts_the_game_and_start_raises__should_fail_the_game(self):
        game_service = MockGameService()
        game_service.start_game = MagicMock(side_effect=RuntimeError("start failed"))
        session_manager = SessionManager(game_service)
        router = MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)
        ticket = make_test_game_ticket(username="Alice", room_id="game1", user_id="user-0")
        specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
        session_manager.create_pending_game(game_id="game1", player_specs=specs, num_ai_players=3)
        connection = MockConnection(game_id="game1")
        router.handle_connect(connection)

        await router.handle_message(connection, {"t": WireClientMessageType.JOIN_GAME, "game_ticket": ticket})
        await wait_for_background_tasks(session_manager)
        assert session_manager.get_game("game1") is None
        assert [m["code"] for m in connection.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
        assert connection._close_code == 1011

    async def test_message_router__when_the_ai_replacement_on_disconnect_raises__should_fail_the_game(self):
        session_manager = SessionManager(MockGameService())
        router = MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)
        conns = await create_started_game(session_manager, num_ai_players=2, player_names=["Alice", "Bob"])
        session_manager._game_service.process_ai_player_actions_after_replacement = MagicMock(
            side_effect=ValueError("engine state broke"),
        )

        await router.handle_disconnect(conns[0])
        await wait_for_background_tasks(session_manager)
        assert session_manager.get_game("game1") is None
        assert conns[0].connection_id not in session_manager._connections
        assert (conns[1]._close_code, conns[1]._close_reason) == (1011, "internal_error")
