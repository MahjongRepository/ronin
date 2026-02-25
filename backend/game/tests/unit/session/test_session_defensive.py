import asyncio
import contextlib
from unittest.mock import AsyncMock

from game.logic.enums import GameAction, GameErrorCode
from game.logic.events import BroadcastTarget, ErrorEvent, EventType, ServiceEvent
from game.messaging.types import SessionErrorCode, SessionMessageType
from game.server.types import PlayerSpec
from game.session.manager import SessionManager
from game.tests.helpers.auth import make_test_game_ticket
from game.tests.mocks import MockConnection, MockGameService

from .helpers import create_started_game


class TestSessionManagerDefensiveChecks:
    """Tests for defensive checks that guard against invalid state."""

    async def test_handle_game_action_not_in_game_returns_error(self, manager):
        """Performing a game action without joining returns an error."""
        conn = MockConnection()
        manager.register_connection(conn)

        await manager.handle_game_action(conn, GameAction.DISCARD, {})

        assert len(conn.sent_messages) == 1
        msg = conn.sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.NOT_IN_GAME

    async def test_leave_game_when_game_is_none(self, manager):
        """Leaving when the game mapping is missing clears player state and does not raise."""
        conns = await create_started_game(manager, "game1")

        player = manager._players[conns[0].connection_id]

        # remove the game from the internal mapping to simulate the defensive case
        manager._games.pop(player.game_id, None)

        # should return without error and clear player game association
        await manager.leave_game(conns[0])
        assert player.game_id is None
        assert player.seat is None

    async def test_handle_game_action_game_is_none(self, manager):
        """Performing a game action when game is missing from mapping does not raise."""
        conns = await create_started_game(manager, "game1")
        conns[0]._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)

        # should return silently without error
        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})
        assert len(conns[0].sent_messages) == 0

    async def test_handle_game_action_no_lock_returns_error(self, manager):
        """Performing a game action when the game has no lock (edge case) returns an error."""
        conns = await create_started_game(manager, "game1")
        conns[0]._outbox.clear()

        # remove lock to simulate edge case
        manager._game_locks.pop("game1", None)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})
        assert len(conns[0].sent_messages) == 1
        msg = conns[0].sent_messages[0]
        assert msg["type"] == SessionMessageType.ERROR
        assert msg["code"] == SessionErrorCode.GAME_NOT_STARTED

    async def test_broadcast_chat_game_is_none(self, manager):
        """Broadcasting chat when game is missing from mapping does not raise."""
        conns = await create_started_game(manager, "game1")
        conns[0]._outbox.clear()

        # remove the game from the internal mapping
        manager._games.pop("game1", None)

        # should return silently without error
        await manager.broadcast_chat(conns[0], "hello")
        assert len(conns[0].sent_messages) == 0

    async def test_cancel_all_pending_timeouts(self):
        """cancel_all_pending_timeouts cancels timeout tasks for pending games."""
        game_service = MockGameService()
        manager = SessionManager(game_service)

        ticket = make_test_game_ticket("Alice", "game1", user_id="user-0")
        specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
        manager.create_pending_game("game1", specs, num_ai_players=3)

        # Verify pending game exists and has a timeout task
        pending = manager._pending_games.get("game1")
        assert pending is not None
        assert pending.timeout_task is not None
        assert not pending.timeout_task.done()

        manager.cancel_all_pending_timeouts()

        # Allow event loop to process the cancellation
        with contextlib.suppress(asyncio.CancelledError):
            await pending.timeout_task

        assert pending.timeout_task.cancelled()

    async def test_start_game_failure_rolls_back_started_flag(self):
        """When start_game returns an ErrorEvent, game.started is rolled back."""
        game_service = MockGameService()

        # patch start_game to return an error (simulating unsupported settings)
        error_events = [
            ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(
                    code=GameErrorCode.INVALID_ACTION,
                    message="unsupported settings",
                    target="all",
                ),
                target=BroadcastTarget(),
            ),
        ]
        game_service.start_game = AsyncMock(return_value=error_events)  # type: ignore[assignment]
        manager = SessionManager(game_service)

        ticket = make_test_game_ticket("Alice", "game1", user_id="user-0")
        specs = [PlayerSpec(name="Alice", user_id="user-0", game_ticket=ticket)]
        manager.create_pending_game("game1", specs, num_ai_players=3)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", ticket)

        # game.started should be rolled back to False
        game = manager.get_game("game1")
        assert game is not None
        assert game.started is False

        # no lock or heartbeat resources should be allocated
        assert "game1" not in manager._game_locks
