from game.logic.enums import GameAction
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.session.models import PlayerSpec
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MOCK_AWAITING, MockConnection

from .helpers import game_of


class TestSessionManagerDefensiveChecks:
    async def test_handle_game_action__when_connection_not_in_game__should_return_not_in_game_error(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.handle_game_action(conn, action=GameAction.DISCARD, data={}, wait_id=MOCK_AWAITING.wait_id)
        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NOT_IN_GAME

    async def test_shutdown__when_game_pending__should_cancel_timeout_task(self, manager):
        ticket = make_test_game_ticket(username="Alice", room_id="game1", user_id="user-0")
        manager.create_pending_game(
            game_id="game1",
            player_specs=[PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)],
        )
        pending_timeout = game_of(manager).pending_timeout
        assert pending_timeout is not None
        assert not pending_timeout.done()

        await manager.shutdown()
        assert pending_timeout.cancelled()
