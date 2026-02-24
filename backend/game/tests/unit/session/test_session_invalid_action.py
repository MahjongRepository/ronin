import logging
from unittest.mock import AsyncMock

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, ServiceEvent
from game.logic.exceptions import InvalidGameActionError
from game.messaging.event_payload import EVENT_TYPE_INT
from game.messaging.types import SessionMessageType
from game.tests.mocks import MockResultEvent

from .helpers import create_started_game

DISCARD_ERROR = InvalidGameActionError(action="discard", seat=0, reason="tile not in hand")


class TestSessionManagerInvalidAction:
    """Tests for InvalidGameActionError handling: disconnect + AI player replacement."""

    async def test_invalid_action_disconnects_player(self, manager):
        """Player sends invalid action -> connection closed with code 1008."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        assert conns[0]._close_reason == "invalid_game_action"

    async def test_invalid_action_replaces_with_ai_player(self, manager):
        """After disconnect, AI player replaces the player."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_with_ai_player = tracking_replace
        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        assert len(replace_calls) == 1
        assert replace_calls[0] == ("game1", "Alice")

    async def test_invalid_action_broadcasts_player_left(self, manager):
        """Other players receive a player_left message when the offender is disconnected."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        left_msgs = [m for m in conns[1].sent_messages if m.get("type") == SessionMessageType.PLAYER_LEFT]
        assert len(left_msgs) == 1
        assert left_msgs[0]["player_name"] == "Alice"

    async def test_invalid_action_last_player_cleans_up_game(self, manager):
        """If the offender was the last player, game is cleaned up."""
        conns = await create_started_game(manager, "game1", num_ai_players=3, player_names=["Alice"])
        assert manager.get_game("game1") is not None

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # game should be cleaned up
        assert manager.get_game("game1") is None

    async def test_invalid_action_logs_warning(self, manager, caplog):
        """The warning log contains action and reason as structured fields."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        with caplog.at_level(logging.WARNING):
            await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1
        msg = warning_records[0].msg
        assert msg["event"] == "invalid game action"
        assert msg["action"] == "discard"
        assert msg["reason"] == "tile not in hand"

    async def test_invalid_action_ai_player_processes_pending_actions(self, manager):
        """After AI player replacement, pending AI player actions are processed and broadcast."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        ai_player_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="AI",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=[ai_player_event],
        )
        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # Bob should receive the AI player action event
        ai_player_msgs = [m for m in conns[1].sent_messages if m.get("t") == EVENT_TYPE_INT[EventType.DRAW]]
        assert len(ai_player_msgs) == 1

    async def test_resolution_triggered_attribution_disconnects_offender(self, manager):
        """When seat A triggers resolution that fails on seat B's data, seat B is disconnected."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # Seat 0 (Alice) sends PASS, but resolution fails on seat 1 (Bob)'s prior bad chi data.
        resolution_error = InvalidGameActionError(
            action="resolve_call",
            seat=1,
            reason="chi tile not in hand",
        )
        manager._game_service.handle_action = AsyncMock(side_effect=resolution_error)

        # Alice (seat 0) sends the action that triggers the error
        await manager.handle_game_action(conns[0], GameAction.PASS, {})

        # Bob (seat 1, the offender) should be disconnected
        assert conns[1].is_closed
        assert conns[1]._close_code == 1008

        # Alice (seat 0, innocent) should NOT be disconnected
        assert not conns[0].is_closed

    async def test_handle_invalid_action_ai_replacement_raises_invalid_game_action_error(self, manager):
        """If AI replacement raises InvalidGameActionError blaming another seat, player is still disconnected."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        # AI replacement flow raises InvalidGameActionError blaming a different seat
        ai_replacement_error = InvalidGameActionError(
            action="resolve_call",
            seat=1,
            reason="resolution failed on prior bad data from another seat",
        )
        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            side_effect=ai_replacement_error,
        )

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # original offender (seat 0) should still be disconnected
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008

    async def test_leave_game_returns_early_after_invalid_action(self, manager):
        """When leave_game is called after invalid action disconnect, it returns early (no double cleanup)."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.handle_action = AsyncMock(side_effect=DISCARD_ERROR)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # player.game_id is now None, so leave_game should return early
        replace_calls = []
        original_replace = manager._game_service.replace_with_ai_player

        def tracking_replace(game_id, player_name):
            replace_calls.append((game_id, player_name))
            return original_replace(game_id, player_name)

        manager._game_service.replace_with_ai_player = tracking_replace

        # simulate the WebSocket disconnect handler calling leave_game
        await manager.leave_game(conns[0])

        # no additional replacement should have happened
        assert len(replace_calls) == 0

    async def test_invalid_action_seat_not_found_skips_disconnect(self, manager):
        """When the error seat doesn't map to a connected player (AI player seat), skip disconnect."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # error references seat 3 (an AI player seat, no connected player)
        error = InvalidGameActionError(action="discard", seat=3, reason="bad data")
        manager._game_service.handle_action = AsyncMock(side_effect=error)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # neither player should be disconnected (offending seat is an AI player)
        assert not conns[0].is_closed
        assert not conns[1].is_closed


class TestTimeoutInvalidActionHandling:
    """Tests for _handle_timeout catching InvalidGameActionError."""

    async def test_timeout_invalid_action_disconnects_offender(self, manager):
        """When a timeout triggers an InvalidGameActionError, the offender is disconnected."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        # make handle_timeout raise InvalidGameActionError for seat 0
        error = InvalidGameActionError(action="pass", seat=0, reason="resolution failed on bad data")
        manager._game_service.handle_timeout = AsyncMock(side_effect=error)

        await manager._handle_timeout("game1", TimeoutType.MELD, 0)

        # offender (seat 0) should be disconnected
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008

        # innocent player (seat 1) should NOT be disconnected
        assert not conns[1].is_closed

    async def test_timeout_ai_replacement_raises_invalid_game_action_error(self, manager):
        """When AI replacement after timeout raises InvalidGameActionError, offender is still disconnected."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        error = InvalidGameActionError(action="pass", seat=0, reason="resolution failed")
        manager._game_service.handle_timeout = AsyncMock(side_effect=error)

        # AI replacement flow raises InvalidGameActionError blaming a different seat
        ai_replacement_error = InvalidGameActionError(
            action="resolve_call",
            seat=1,
            reason="resolution failed on prior bad data",
        )
        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            side_effect=ai_replacement_error,
        )

        await manager._handle_timeout("game1", TimeoutType.MELD, 0)

        # original offender (seat 0) should still be disconnected
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008

        # innocent player (seat 1) should NOT be disconnected
        assert not conns[1].is_closed

    async def test_timeout_invalid_action_cleans_up_last_player(self, manager):
        """When timeout disconnects the last player, the game is cleaned up."""
        conns = await create_started_game(manager, "game1", num_ai_players=3, player_names=["Alice"])

        error = InvalidGameActionError(action="pass", seat=0, reason="resolution error")
        manager._game_service.handle_timeout = AsyncMock(side_effect=error)

        await manager._handle_timeout("game1", TimeoutType.MELD, 0)

        assert conns[0].is_closed
        assert manager.get_game("game1") is None
