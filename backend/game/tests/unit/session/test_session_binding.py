"""Tests for session token integration with SessionManager.

Verify seat binding on start, disconnect marking on leave, and cleanup on game end.
"""

from game.logic.exceptions import InvalidGameActionError
from game.session.models import Game, Player
from game.tests.mocks import MockConnection

from .helpers import create_started_game


class TestSeatBindingOnStart:
    async def test_game_start_binds_seat_to_session(self, manager):
        """After game starts, session data has the assigned seat number."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        player1 = manager._players.get(conns[0].connection_id)
        player2 = manager._players.get(conns[1].connection_id)

        session1 = manager._session_store._sessions.get(player1.session_token)
        session2 = manager._session_store._sessions.get(player2.session_token)
        assert session1 is not None
        assert session2 is not None
        assert session1.seat == 0
        assert session2.seat == 1


class TestSessionDisconnect:
    async def test_leave_started_game_marks_session_disconnected(self, manager):
        """Leaving a started game marks the session as disconnected (not removed)."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        player1 = manager._players.get(conns[0].connection_id)
        token1 = player1.session_token

        await manager.leave_game(conns[0])

        session = manager._session_store._sessions.get(token1)
        assert session is not None
        assert session.disconnected_at is not None

    async def test_leave_game_missing_game_removes_session(self, manager):
        """When player.game_id is set but game mapping is missing, session is removed."""
        conns = await create_started_game(manager, "game1")

        player = manager._players.get(conns[0].connection_id)
        token = player.session_token

        # simulate game mapping disappearing (race condition / defensive path)
        manager._games.pop("game1", None)

        await manager.leave_game(conns[0])

        session = manager._session_store._sessions.get(token)
        assert session is None


class TestSessionCleanup:
    async def test_game_cleanup_removes_all_sessions(self, manager):
        """When the last player leaves and game is cleaned up, all sessions are removed."""
        conns = await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        player1 = manager._players.get(conns[0].connection_id)
        player2 = manager._players.get(conns[1].connection_id)
        token1 = player1.session_token
        token2 = player2.session_token

        # both leave, triggering cleanup
        await manager.leave_game(conns[0])
        await manager.leave_game(conns[1])

        assert manager._session_store._sessions.get(token1) is None
        assert manager._session_store._sessions.get(token2) is None
        assert manager.get_game("game1") is None


class TestInvalidActionSessionTracking:
    async def test_invalid_action_marks_session_disconnected(self, manager):
        """_handle_invalid_action marks the offender's session as disconnected."""
        conn = MockConnection()
        manager.register_connection(conn)
        game_obj = Game(game_id="game1")
        game_obj.started = True
        manager._games["game1"] = game_obj

        # manually create player with session
        session = manager._session_store.create_session("Alice", "game1")
        player = Player(
            connection=conn,
            name="Alice",
            session_token=session.session_token,
            game_id="game1",
            seat=0,
        )
        game_obj.players[conn.connection_id] = player
        manager._players[conn.connection_id] = player
        manager._connections[conn.connection_id] = conn

        error = InvalidGameActionError(seat=0, action="discard", reason="test error")
        await manager._handle_invalid_action(game_obj, conn, player, error)

        session_after = manager._session_store._sessions.get(session.session_token)
        assert session_after is not None
        assert session_after.disconnected_at is not None
