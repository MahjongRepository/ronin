from unittest.mock import AsyncMock, patch

from game.logic.enums import GameAction
from game.logic.events import BroadcastTarget, EventType, GameEndedEvent, ServiceEvent
from game.logic.types import GameEndResult, PlayerStanding
from game.session.models import Player
from game.tests.mocks import MockConnection, MockResultEvent

from .helpers import make_game_with_human


class TestSessionManagerGameEnd:
    """Tests for connection closing on game end."""

    def _make_game_end_event(self) -> ServiceEvent:
        return ServiceEvent(
            event=EventType.GAME_END,
            data=GameEndedEvent(
                type=EventType.GAME_END,
                target="all",
                result=GameEndResult(
                    winner_seat=0,
                    standings=[
                        PlayerStanding(seat=0, name="Alice", score=25000, final_score=0, is_bot=False),
                    ],
                ),
            ),
            target=BroadcastTarget(),
        )

    async def test_close_connections_on_game_end(self, manager):
        """All player connections are closed when game_end event is present."""
        game, _player, conn = make_game_with_human(manager)

        events = [self._make_game_end_event()]
        await manager._close_connections_on_game_end(game, events)

        assert conn.is_closed is True
        assert conn._close_code == 1000
        assert conn._close_reason == "game_ended"

    async def test_close_connections_skipped_without_game_end(self, manager):
        """Connections are not closed when no game_end event is present."""
        game, _player, conn = make_game_with_human(manager)

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
        game, _player, conn1 = make_game_with_human(manager)

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
        """close_game_on_error closes all player connections in the game."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        await manager.close_game_on_error(conn1)

        assert conn1.is_closed
        assert conn2.is_closed
        assert conn1._close_code == 1011
        assert conn1._close_reason == "internal_error"

    async def test_close_game_on_error_no_player(self, manager):
        """close_game_on_error does nothing for unregistered connection."""
        conn = MockConnection()
        manager.register_connection(conn)

        # should not raise
        await manager.close_game_on_error(conn)

        assert not conn.is_closed

    async def test_close_game_on_error_game_is_none(self, manager):
        """close_game_on_error does nothing when game has been removed."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        # remove the game from the internal mapping to simulate cleanup race
        manager._games.pop("game1", None)

        # should return without error
        await manager.close_game_on_error(conn)

        # connection should NOT be closed (game is gone)
        assert not conn.is_closed

    async def test_heartbeat_stops_on_game_cleanup(self, manager):
        """Heartbeat task is cancelled when game becomes empty."""
        conns = [MockConnection() for _ in range(4)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        assert "game1" in manager._heartbeat._tasks
        heartbeat_task = manager._heartbeat._tasks.get("game1")

        # leave all players -- game becomes empty, cleanup runs
        for c in conns:
            await manager.leave_game(c)

        assert "game1" not in manager._heartbeat._tasks
        assert heartbeat_task.done()

    async def test_heartbeat_loop_stops_when_game_removed(self, manager):
        """Heartbeat loop returns when the game is no longer in the games dict."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")
        await manager.join_game(conn, "game1", "Alice")

        # remove the game from the dict
        manager._games.pop("game1", None)

        with patch("game.session.heartbeat.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_sleep.return_value = None
            # should return without error when game is missing
            await manager._heartbeat._loop("game1", manager.get_game)

        assert not conn.is_closed
