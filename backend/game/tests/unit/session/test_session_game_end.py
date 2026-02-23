from unittest.mock import AsyncMock, patch

from game.logic.enums import GameAction, TimeoutType
from game.logic.events import BroadcastTarget, EventType, GameEndedEvent, ServiceEvent
from game.logic.exceptions import InvalidGameActionError
from game.logic.types import PlayerStanding
from game.session.models import Player
from game.tests.mocks import MockConnection, MockResultEvent

from .helpers import create_started_game, make_game_with_player


def _make_game_end_events() -> list[ServiceEvent]:
    return [
        ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                winner_seat=0,
                standings=[
                    PlayerStanding(seat=0, score=25000, final_score=0),
                ],
            ),
            target=BroadcastTarget(),
        ),
    ]


class TestSessionManagerGameEnd:
    """Tests for connection closing on game end."""

    def _make_game_end_event(self) -> ServiceEvent:
        return ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                winner_seat=0,
                standings=[
                    PlayerStanding(seat=0, score=25000, final_score=0),
                ],
            ),
            target=BroadcastTarget(),
        )

    async def test_close_connections_on_game_end(self, manager):
        """All player connections are closed when game_end event is present."""
        game, _player, conn = make_game_with_player(manager)

        events = [self._make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)

        assert conn.is_closed is True
        assert conn._close_code == 1000
        assert conn._close_reason == "game_ended"

    async def test_close_connections_skipped_without_game_end(self, manager):
        """Connections are not closed when no game_end event is present."""
        game, _player, conn = make_game_with_player(manager)

        generic_event = ServiceEvent(
            event=EventType.DRAW,
            data=MockResultEvent(
                type=EventType.DRAW,
                target="all",
                player="Alice",
                action=GameAction.DISCARD,
                input={},
                success=True,
            ),
            target=BroadcastTarget(),
        )
        await manager._close_connections_on_game_end(game, [generic_event])

        assert conn.is_closed is False

    async def test_close_connections_on_game_end_multiple_players(self, manager):
        """All player connections are closed when game ends with multiple players."""
        game, _player, conn1 = make_game_with_player(manager)

        conn2 = MockConnection()
        player2 = Player(connection=conn2, name="Bob", session_token="tok-bob", game_id="game1", seat=1)
        game.players[conn2.connection_id] = player2

        events = [self._make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)

        assert conn1.is_closed is True
        assert conn2.is_closed is True


class TestSessionManagerCloseGameOnError:
    """Tests for close_game_on_error method."""

    async def test_close_game_on_error_closes_all_connections(self, manager):
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        await manager.close_game_on_error(conns[0])

        assert conns[0].is_closed
        assert conns[1].is_closed
        assert conns[0]._close_code == 1011
        assert conns[0]._close_reason == "internal_error"

    async def test_close_game_on_error_no_player(self, manager):
        """close_game_on_error does nothing for unregistered connection."""
        conn = MockConnection()
        manager.register_connection(conn)

        # should not raise
        await manager.close_game_on_error(conn)

        assert not conn.is_closed

    async def test_close_game_on_error_game_is_none(self, manager):
        """close_game_on_error does nothing when game has been removed."""
        conns = await create_started_game(manager, "game1")

        # remove the game from the internal mapping to simulate cleanup race
        manager._games.pop("game1", None)

        # should return without error
        await manager.close_game_on_error(conns[0])

        # connection should NOT be closed (game is gone)
        assert not conns[0].is_closed

    async def test_heartbeat_stops_on_game_cleanup(self, manager):
        """Heartbeat task is cancelled when game becomes empty."""
        conns = await create_started_game(
            manager,
            "game1",
            num_ai_players=0,
            player_names=["P0", "P1", "P2", "P3"],
        )

        assert "game:game1" in manager._heartbeat._tasks
        heartbeat_task = manager._heartbeat._tasks.get("game:game1")

        # leave all players -- game becomes empty, cleanup runs
        for c in conns:
            await manager.leave_game(c)

        assert "game:game1" not in manager._heartbeat._tasks
        assert heartbeat_task.done()

    async def test_heartbeat_loop_stops_when_game_removed(self, manager):
        """Heartbeat loop returns when the game is no longer in the games dict."""
        conns = await create_started_game(manager, "game1")

        # remove the game from the dict
        manager._games.pop("game1", None)

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.return_value = None
            # should return without error when game is missing
            await manager._heartbeat._check_loop("game1", "game", manager.get_game)

        assert not conns[0].is_closed


class TestGameEndFromAction:
    """Tests that handle_game_action closes connections when game ends."""

    async def test_successful_action_game_end_closes_connections(self, manager):
        """handle_game_action closes connections when a successful action ends the game."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.handle_action = AsyncMock(return_value=_make_game_end_events())

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        assert conns[0].is_closed
        assert conns[0]._close_code == 1000
        assert conns[0]._close_reason == "game_ended"
        assert conns[1].is_closed

    async def test_invalid_action_ai_replacement_game_end_closes_connections(self, manager):
        """When AI replacement after invalid action ends the game, connections close."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=_make_game_end_events(),
        )
        error = InvalidGameActionError(action="discard", seat=0, reason="bad tile")
        manager._game_service.handle_action = AsyncMock(side_effect=error)

        await manager.handle_game_action(conns[0], GameAction.DISCARD, {})

        # Offender closed with 1008 (invalid action)
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        # Bob closed with 1000 (game ended via AI replacement)
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000
        assert conns[1]._close_reason == "game_ended"


class TestGameEndFromTimeout:
    """Tests that _handle_timeout closes connections when game ends."""

    async def test_timeout_game_end_closes_connections(self, manager):
        """_handle_timeout closes connections when the game ends normally."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.handle_timeout = AsyncMock(return_value=_make_game_end_events())

        await manager._handle_timeout("game1", TimeoutType.TURN, 0)

        assert conns[0].is_closed
        assert conns[0]._close_code == 1000
        assert conns[0]._close_reason == "game_ended"
        assert conns[1].is_closed

    async def test_timeout_invalid_action_ai_game_end_closes_connections(self, manager):
        """When timeout leads to invalid action + AI replacement ending the game."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=_make_game_end_events(),
        )
        error = InvalidGameActionError(action="pass", seat=0, reason="resolution failed")
        manager._game_service.handle_timeout = AsyncMock(side_effect=error)

        await manager._handle_timeout("game1", TimeoutType.MELD, 0)

        # Offender closed with 1008
        assert conns[0].is_closed
        assert conns[0]._close_code == 1008
        # Bob closed with 1000 (game ended)
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000


class TestGameEndFromLeaveGame:
    """Tests that leave_game closes connections when AI replacement ends the game."""

    async def test_leave_game_ai_replacement_game_end_closes_connections(self, manager):
        """When AI replacement after disconnect ends the game, connections close."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        manager._game_service.process_ai_player_actions_after_replacement = AsyncMock(
            return_value=_make_game_end_events(),
        )

        await manager.leave_game(conns[0])

        # Bob's connection should be closed with game_ended
        assert conns[1].is_closed
        assert conns[1]._close_code == 1000
        assert conns[1]._close_reason == "game_ended"
