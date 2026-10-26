import logging
from unittest.mock import MagicMock

import pytest

from game.messaging.types import (
    SessionErrorCode,
    SessionMessageType,
)
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.server.router import MessageRouter
from game.session.models import PlayerSpec
from game.tests.helpers.auth import TEST_TICKET_SECRET, make_test_game_ticket
from game.tests.helpers.session import make_session_manager
from game.tests.mocks import MockConnection, MockGameService
from game.tests.unit.session.helpers import create_started_game, wait_for_background_tasks


def _setup_player_in_game(session_manager, connection):
    ticket = make_test_game_ticket(username="Alice", room_id="game1", user_id="user-0")
    specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
    session_manager.create_pending_game(game_id="game1", player_specs=specs)
    session_manager.join_game(connection, game_id="game1", session_token=ticket)
    connection._outbox.clear()


class TestMessageRouterBranches:
    @pytest.fixture
    async def setup(self):
        game_service = MockGameService()
        session_manager = make_session_manager(game_service)
        router = MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)
        connection = MockConnection()
        router.handle_connect(connection)
        return router, connection, session_manager

    async def test_message_router__when_reconnect_without_session__should_return_no_session_error(self, setup):
        router, connection, _ = setup

        ticket = make_test_game_ticket(username="Alice", room_id="test-game")
        router.handle_message(
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

        router.handle_message(
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
        session_manager.create_pending_game(game_id="test-game", player_specs=specs)

        router.handle_message(
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

        router.handle_disconnect(connection)
        assert len(connection.sent_messages) == 0

    async def test_message_router__when_message_invalid__should_return_invalid_message_error_without_the_input(
        self, setup, caplog
    ):
        router, connection, _ = setup
        ticket_in_the_type_tag = make_test_game_ticket(username="Alice", room_id="test-game")

        with caplog.at_level(logging.WARNING):
            router.handle_message(connection, {"t": ticket_in_the_type_tag})
        assert len(connection.sent_messages) == 1
        response = connection.sent_messages[0]
        assert response["type"] == SessionMessageType.ERROR
        assert response["code"] == SessionErrorCode.INVALID_MESSAGE
        assert ticket_in_the_type_tag not in str(response)
        assert [(r.msg["event"], r.msg["error_types"], r.msg["error_count"]) for r in caplog.records] == [
            ("invalid message", ["union_tag_invalid"], 1)
        ]
        assert ticket_in_the_type_tag not in caplog.text

    async def test_message_router__when_game_action_lacks_the_wait_id__should_refuse_it_as_invalid_message(self, setup):
        router, connection, session_manager = setup
        _setup_player_in_game(session_manager, connection)
        session_manager.handle_game_action = MagicMock()

        router.handle_message(
            connection, {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": 0}
        )
        assert [(m["type"], m["code"]) for m in connection.sent_messages] == [
            (SessionMessageType.ERROR, SessionErrorCode.INVALID_MESSAGE)
        ]
        session_manager.handle_game_action.assert_not_called()

    async def test_message_router__when_game_action_raises__should_fail_the_players_game(self, setup):
        router, connection, session_manager = setup
        _setup_player_in_game(session_manager, connection)
        session_manager.handle_game_action = MagicMock(side_effect=ValueError("engine state broke"))

        router.handle_message(
            connection,
            {
                "t": WireClientMessageType.GAME_ACTION,
                "wi": 0,
                "a": WireGameAction.DISCARD,
                "ti": 0,
            },
        )
        await wait_for_background_tasks(session_manager)
        assert session_manager.get_game("game1") is None
        assert [m["code"] for m in connection.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
        assert connection._close_code == 1011

    async def test_message_router__when_join_raises_outside_any_game__should_log_and_close_with_1011(
        self, setup, caplog
    ):
        router, connection, session_manager = setup
        session_manager.join_game = MagicMock(side_effect=KeyError("session store broke"))
        ticket = make_test_game_ticket(username="Alice", room_id=connection.game_id)

        with caplog.at_level(logging.ERROR):
            router.handle_message(connection, {"t": WireClientMessageType.JOIN_GAME, "game_ticket": ticket})
        assert [r.msg["event"] for r in caplog.records if r.levelno == logging.ERROR] == [
            "connection failed outside a game"
        ]
        assert [m["code"] for m in connection.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
        assert connection._close_code == 1011


class TestMessageRouterEntryPointFailures:
    async def test_message_router__when_the_final_join_starts_the_game_and_start_raises__should_fail_the_game(self):
        game_service = MockGameService()
        game_service.start_game = MagicMock(side_effect=RuntimeError("start failed"))
        session_manager = make_session_manager(game_service)
        router = MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)
        ticket = make_test_game_ticket(username="Alice", room_id="game1", user_id="user-0")
        specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
        session_manager.create_pending_game(game_id="game1", player_specs=specs)
        connection = MockConnection(game_id="game1")
        router.handle_connect(connection)

        router.handle_message(connection, {"t": WireClientMessageType.JOIN_GAME, "game_ticket": ticket})
        await wait_for_background_tasks(session_manager)
        assert session_manager.get_game("game1") is None
        assert [m["code"] for m in connection.sent_messages] == [SessionErrorCode.INTERNAL_ERROR]
        assert connection._close_code == 1011

    async def test_message_router__when_the_ai_replacement_on_disconnect_raises__should_fail_the_game(self):
        game_service = MockGameService()
        session_manager = make_session_manager(game_service)
        router = MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)
        conns = create_started_game(session_manager, player_names=["Alice", "Bob"])
        game_service.process_ai_player_actions_after_replacement = MagicMock(
            side_effect=ValueError("engine state broke"),
        )

        router.handle_disconnect(conns[0])
        await wait_for_background_tasks(session_manager)
        assert session_manager.get_game("game1") is None
        assert conns[0].connection_id not in session_manager._connections
        assert (conns[1]._close_code, conns[1]._close_reason) == (1011, "internal_error")
