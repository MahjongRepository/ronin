import logging
from unittest.mock import AsyncMock

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, ServiceEvent
from game.logic.exceptions import InvalidGameActionError
from game.messaging.types import SessionMessageType
from game.tests.mocks import MockConnection, MockResultEvent

DISCARD_ERROR = InvalidGameActionError(action="discard", seat=0, reason="tile not in hand")


class TestSessionManagerInvalidAction:
    """Tests for InvalidGameActionError handling: disconnect + bot replacement."""

    async def test_invalid_action_disconnects_player(self, manager):
        """Player sends invalid action -> connection closed with code 1008."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        assert conns[0]._close_reason == "invalid_game_action"

    async def test_invalid_action_replaces_with_bot(self, manager):
        """After disconnect, bot replaces the player."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace
        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", "Alice")

    async def test_invalid_action_broadcasts_player_left(self, manager):
        """Other players receive a player_left message when the offender is disconnected."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")
        conns[1]._outbox.clear()

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        left_msgs = [m for m in conns[1].sent_messages if m.get("type") == SessionMessageType.PLAYER_LEFT]
        assert len(left_msgs) == 1
        assert left_msgs[0]["player_name"] == "Alice"

    async def test_invalid_action_game_continues_for_others(self, manager):
        """After disconnect + bot replacement, other humans can still play."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # game should still exist (Bob is still in)
        assert manager.get_game("game1") is not None
        assert not conns[1].is_closed

    async def test_invalid_action_removes_player_state(self, manager):
        """After invalid action, player's game_id and seat are cleared."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        player = manager._players[conns[0].connection_id]

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        assert player.game_id is None
        assert player.seat is None

    async def test_invalid_action_cancels_player_timer(self, manager):
        """The disconnected player's timer is cancelled."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        # verify timer exists for seat 0
        assert manager._timer_manager.get_timer("game1", 0) is not None

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # seat 0's timer should be removed
        assert manager._timer_manager.get_timer("game1", 0) is None
        # seat 1's timer should remain
        assert manager._timer_manager.get_timer("game1", 1) is not None

    async def test_invalid_action_last_human_cleans_up_game(self, manager):
        """If the offender was the last human, game is cleaned up."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=3)

        await manager.join_game(conn, "game1", "Alice")
        assert manager.get_game("game1") is not None

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conn, GameAction.DISCARD, {})

        # game should be cleaned up
        assert manager.get_game("game1") is None

    async def test_invalid_action_logs_warning(self, manager, caplog):
        """The warning log contains game_id, user_id, player_name, seat, action, and reason."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        with caplog.at_level(logging.WARNING):
            await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        warning_msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_msgs) >= 1
        msg = warning_msgs[0].message
        assert "game1" in msg
        assert conns[0].connection_id in msg
        assert "Alice" in msg
        assert "seat=0" in msg
        assert "discard" in msg
        assert "tile not in hand" in msg

    async def test_invalid_action_bot_processes_pending_actions(self, manager):
        """After bot replacement, pending bot actions are processed and broadcast."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")
        conns[1]._outbox.clear()

        bot_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="Bot",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        manager._game_service.process_bot_actions_after_replacement = AsyncMock(return_value=[bot_event])
        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # Bob should receive the bot action event
        bot_msgs = [m for m in conns[1].sent_messages if m.get("type") == EventType.DRAW]
        assert len(bot_msgs) == 1

    async def test_resolution_triggered_attribution_disconnects_offender(self, manager):
        """When seat A triggers resolution that fails on seat B's data, seat B is disconnected."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")  # seat 0
        await manager.join_game(conns[1], "game1", "Bob")  # seat 1

        # Seat 0 (Alice) sends PASS, but resolution fails on seat 1 (Bob)'s prior bad chi data.
        # The exception has seat=1, identifying the offender.
        resolution_error = InvalidGameActionError(
            action="resolve_call", seat=1, reason="chi tile not in hand"
        )
        manager._game_service.handle_action = AsyncMock(side_effect=resolution_error)

        # Alice (seat 0) sends the action that triggers the error
        await manager.handle_game_action(conns[0], GameAction.PASS, {})

        # Bob (seat 1, the offender) should be disconnected
        assert conns[1].is_closed
        assert conns[1]._close_code == 1008

        # Alice (seat 0, innocent) should NOT be disconnected
        assert not conns[0].is_closed

    async def test_handle_invalid_action_failure_still_disconnects(self, manager):
        """If _replace_with_bot raises during invalid action handling, player is still disconnected."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        # make process_bot_actions_after_replacement raise an exception
        manager._game_service.process_bot_actions_after_replacement = AsyncMock(
            side_effect=RuntimeError("bot processing failed")
        )

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # player should still be disconnected despite the error during bot replacement
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008

    async def test_leave_game_returns_early_after_invalid_action(self, manager):
        """When leave_game is called after invalid action disconnect, it returns early (no double cleanup)."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # player.game_id is now None, so leave_game should return early
        replace_calls = []
        original_replace = manager._game_service.replace_player_with_bot

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_player_with_bot = tracking_replace

        # simulate the WebSocket disconnect handler calling leave_game
        await manager.leave_game(conns[0])

        # no additional replacement should have happened
        assert len(replace_calls) == 0

    async def test_invalid_action_seat_not_found_skips_disconnect(self, manager):
        """When the error seat doesn't map to a connected player (bot seat), skip disconnect."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")  # seat 0
        await manager.join_game(conns[1], "game1", "Bob")  # seat 1

        # error references seat 3 (a bot seat, no connected player)
        error = InvalidGameActionError(action="discard", seat=3, reason="bad data")
        manager._game_service.handle_action = AsyncMock(side_effect=error)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # neither player should be disconnected (offending seat is a bot)
        assert not conns[0].is_closed
        assert not conns[1].is_closed


class TestTimeoutInvalidActionHandling:
    """Tests for _handle_timeout catching InvalidGameActionError."""

    async def test_timeout_invalid_action_disconnects_offender(self, manager):
        """When a timeout triggers an InvalidGameActionError, the offender is disconnected."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        # make handle_timeout raise InvalidGameActionError for seat 0
        error = InvalidGameActionError(action="pass", seat=0, reason="resolution failed on bad data")
        manager._game_service.handle_timeout = AsyncMock(side_effect=error)

        await manager._handle_timeout("game1", TimeoutType.MELD, 0)

        # offender (seat 0) should be disconnected
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008

        # innocent player (seat 1) should NOT be disconnected
        assert not conns[1].is_closed

    async def test_timeout_invalid_action_cleans_up_last_human(self, manager):
        """When timeout disconnects the last human, the game is cleaned up."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=3)

        await manager.join_game(conn, "game1", "Alice")

        error = InvalidGameActionError(action="pass", seat=0, reason="resolution error")
        manager._game_service.handle_timeout = AsyncMock(side_effect=error)

        await manager._handle_timeout("game1", TimeoutType.MELD, 0)

        assert conn.is_closed
        assert manager.get_game("game1") is None


class TestCleanupEmptyGameHelper:
    """Tests for the extracted _cleanup_empty_game helper."""

    async def test_cleanup_empty_game_removes_game(self, manager):
        """_cleanup_empty_game removes an empty game from the registry."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=3)

        await manager.join_game(conn, "game1", "Alice")

        assert manager.get_game("game1") is not None

        # leave via standard path (which uses _cleanup_empty_game)
        await manager.leave_game(conn)

        assert manager.get_game("game1") is None

    async def test_cleanup_nonempty_game_is_noop(self, manager):
        """_cleanup_empty_game does nothing when the game still has players."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        manager.get_game("game1")

        # leave one player
        await manager.leave_game(conns[0])

        # game should still exist
        assert manager.get_game("game1") is not None
