import pytest

from game.logic.enums import WireClientMessageType
from game.messaging.router import MessageRouter
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.session.manager import SessionManager
from game.tests.helpers.auth import TEST_TICKET_SECRET, make_test_game_ticket
from game.tests.mocks import MockConnection, MockGameService


@pytest.fixture
async def setup():
    game_service = MockGameService()
    session_manager = SessionManager(game_service)
    router = MessageRouter(session_manager, game_ticket_secret=TEST_TICKET_SECRET)
    connection = MockConnection()
    await router.handle_connect(connection)
    return router, connection, session_manager


class TestRoomMessageRouting:
    """Tests for room message type routing through the MessageRouter."""

    async def test_join_room_routes_to_session_manager(self, setup):
        router, connection, session_manager = setup
        session_manager.create_room("room1")
        ticket = make_test_game_ticket("Alice", "room1")

        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.JOIN_ROOM,
                "room_id": "room1",
                "game_ticket": ticket,
            },
        )

        assert any(m.get("type") == SessionMessageType.ROOM_JOINED for m in connection.sent_messages)

    async def test_leave_room_routes_to_session_manager(self, setup):
        router, connection, session_manager = setup
        session_manager.create_room("room1")
        ticket = make_test_game_ticket("Alice", "room1")

        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.JOIN_ROOM,
                "room_id": "room1",
                "game_ticket": ticket,
            },
        )
        connection._outbox.clear()

        await router.handle_message(connection, {"t": WireClientMessageType.LEAVE_ROOM})

        assert any(m.get("type") == SessionMessageType.ROOM_LEFT for m in connection.sent_messages)

    async def test_set_ready_routes_to_session_manager(self, setup):
        router, connection, session_manager = setup
        session_manager.create_room("room1", num_ai_players=2)
        ticket = make_test_game_ticket("Alice", "room1")

        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.JOIN_ROOM,
                "room_id": "room1",
                "game_ticket": ticket,
            },
        )
        connection._outbox.clear()

        await router.handle_message(
            connection,
            {"t": WireClientMessageType.SET_READY, "ready": True},
        )

        assert any(m.get("type") == SessionMessageType.PLAYER_READY_CHANGED for m in connection.sent_messages)

    async def test_chat_routes_to_room_when_in_room(self, setup):
        router, connection, session_manager = setup
        session_manager.create_room("room1", num_ai_players=2)
        ticket = make_test_game_ticket("Alice", "room1")

        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.JOIN_ROOM,
                "room_id": "room1",
                "game_ticket": ticket,
            },
        )
        connection._outbox.clear()

        await router.handle_message(
            connection,
            {"t": WireClientMessageType.CHAT, "text": "Hello room!"},
        )

        chat_msgs = [m for m in connection.sent_messages if m.get("type") == SessionMessageType.CHAT]
        assert len(chat_msgs) == 1
        assert chat_msgs[0]["player_name"] == "Alice"
        assert chat_msgs[0]["text"] == "Hello room!"

    async def test_chat_routes_to_game_when_not_in_room(self, setup):
        """Chat goes to game broadcast when player is not in a room."""
        router, connection, _session_manager = setup

        # not in room or game - should get NOT_IN_GAME error
        await router.handle_message(
            connection,
            {"t": WireClientMessageType.CHAT, "text": "Hello!"},
        )

        assert any(m.get("code") == SessionErrorCode.NOT_IN_GAME for m in connection.sent_messages)

    async def test_disconnect_leaves_room(self, setup):
        router, connection, session_manager = setup
        session_manager.create_room("room1")
        ticket = make_test_game_ticket("Alice", "room1")

        await router.handle_message(
            connection,
            {
                "t": WireClientMessageType.JOIN_ROOM,
                "room_id": "room1",
                "game_ticket": ticket,
            },
        )

        await router.handle_disconnect(connection)

        # room should be cleaned up (empty)
        assert session_manager.get_room("room1") is None

    async def test_invalid_room_message_returns_error(self, setup):
        router, connection, _ = setup

        # join_room without required fields
        await router.handle_message(
            connection,
            {"t": WireClientMessageType.JOIN_ROOM},
        )

        assert any(m.get("code") == SessionErrorCode.INVALID_MESSAGE for m in connection.sent_messages)
