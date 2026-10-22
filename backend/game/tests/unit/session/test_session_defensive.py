from game.logic.enums import GameAction
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.session.manager import SessionManager
from game.session.models import PlayerSpec
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MockConnection, MockGameService

from .helpers import create_started_game


class TestSessionManagerDefensiveChecks:
    async def test_handle_game_action__when_connection_not_in_game__should_return_not_in_game_error(self, manager):
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.handle_game_action(conn, action=GameAction.DISCARD, data={})
        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NOT_IN_GAME

    async def test_leave_game__when_game_mapping_missing__should_clear_player_game_and_seat(self, manager):
        conns = await create_started_game(manager)
        player = manager._players[conns[0].connection_id]

        # remove the game from the internal mapping to simulate the defensive case
        manager._games.pop(player.game_id, None)
        # should return without error and clear player game association
        await manager.leave_game(conns[0])
        assert player.game_id is None
        assert player.seat is None

    async def test_handle_game_action__when_game_mapping_missing__should_send_nothing(self, manager):
        conns = await create_started_game(manager)
        conns[0]._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)
        # should return silently without error
        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        assert len(conns[0].sent_messages) == 0

    async def test_handle_game_action__when_game_lock_missing__should_return_game_not_started_error(self, manager):
        conns = await create_started_game(manager)
        conns[0]._outbox.clear()

        # remove lock to simulate edge case
        manager._game_locks.pop("game1", None)
        await manager.handle_game_action(conns[0], action=GameAction.DISCARD, data={})
        assert len(conns[0].sent_messages) == 1
        msg = conns[0].sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.GAME_NOT_STARTED

    async def test_broadcast_chat__when_game_mapping_missing__should_send_nothing(self, manager):
        conns = await create_started_game(manager)
        conns[0]._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)
        # should return silently without error
        await manager.broadcast_chat(conns[0], "hello")
        assert len(conns[0].sent_messages) == 0

    async def test_shutdown__when_game_pending__should_cancel_timeout_task(self):
        game_service = MockGameService()
        manager = SessionManager(game_service)

        ticket = make_test_game_ticket(username="Alice", room_id="game1", user_id="user-0")
        specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
        manager.create_pending_game(game_id="game1", player_specs=specs)
        # Verify pending game exists and has a timeout task
        pending = manager._pending_games.get("game1")
        assert pending is not None
        assert pending.timeout_task is not None
        assert not pending.timeout_task.done()

        await manager.shutdown()
        assert pending.timeout_task.cancelled()
