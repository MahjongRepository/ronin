"""Tests for session token integration with SessionManager.

Verify session creation on join, seat binding on start,
disconnect marking on leave, and cleanup on game end.
"""

from game.logic.exceptions import InvalidGameActionError
from game.messaging.types import SessionMessageType
from game.session.models import Player
from game.tests.mocks import MockConnection


class TestSessionCreationOnJoin:
    async def test_join_game_creates_session_and_returns_token(self, manager):
        """join_game creates a session and includes session_token in game_joined response."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        game_joined = conn.sent_messages[0]
        assert game_joined["type"] == SessionMessageType.GAME_JOINED
        assert "session_token" in game_joined
        assert isinstance(game_joined["session_token"], str)
        assert len(game_joined["session_token"]) > 0

    async def test_session_token_is_unique_per_player(self, manager):
        """Two players joining the same game get different session tokens."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        await manager.join_game(conn2, "game1", "Bob")

        token1 = conn1.sent_messages[0]["session_token"]
        token2 = conn2.sent_messages[0]["session_token"]
        assert token1 != token2

    async def test_join_game_uses_client_session_token(self, manager):
        """join_game uses the client-provided session_token for the session."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice", session_token="client-token")

        game_joined = conn.sent_messages[0]
        assert game_joined["type"] == SessionMessageType.GAME_JOINED
        assert game_joined["session_token"] == "client-token"

    async def test_session_stored_in_session_store(self, manager):
        """Session is accessible in the session store after join."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=2)  # needs 2 humans, so 1 join won't start

        await manager.join_game(conn, "game1", "Alice")

        token = conn.sent_messages[0]["session_token"]
        session = manager._session_store.get_session(token)
        assert session is not None
        assert session.player_name == "Alice"
        assert session.game_id == "game1"
        assert session.seat is None  # not assigned until game start
        assert session.disconnected_at is None


class TestSeatBindingOnStart:
    async def test_game_start_binds_seat_to_session(self, manager):
        """After game starts, session data has the assigned seat number."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        token1 = conn1.sent_messages[0]["session_token"]

        await manager.join_game(conn2, "game1", "Bob")
        token2 = conn2.sent_messages[0]["session_token"]

        # game auto-starts when 2 humans join (num_bots=2)
        session1 = manager._session_store.get_session(token1)
        session2 = manager._session_store.get_session(token2)
        assert session1 is not None
        assert session2 is not None
        assert session1.seat == 0
        assert session2.seat == 1


class TestSessionDisconnect:
    async def test_leave_started_game_marks_session_disconnected(self, manager):
        """Leaving a started game marks the session as disconnected (not removed)."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        token1 = conn1.sent_messages[0]["session_token"]
        await manager.join_game(conn2, "game1", "Bob")

        # game is now started; leave with conn1
        await manager.leave_game(conn1)

        session = manager._session_store.get_session(token1)
        assert session is not None
        assert session.disconnected_at is not None

    async def test_leave_pre_start_game_removes_session(self, manager):
        """Leaving before game starts removes the session entirely."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn, "game1", "Alice")
        token = conn.sent_messages[0]["session_token"]

        # game has not started yet (needs 2 humans, only 1 joined)
        await manager.leave_game(conn)

        session = manager._session_store.get_session(token)
        assert session is None

    async def test_leave_game_missing_game_removes_session(self, manager):
        """When player.game_id is set but game mapping is missing, session is removed."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        token = conn.sent_messages[0]["session_token"]

        # simulate game mapping disappearing (race condition / defensive path)
        manager._games.pop("game1", None)

        await manager.leave_game(conn)

        session = manager._session_store.get_session(token)
        assert session is None

    async def test_leave_game_missing_game_clears_player_state(self, manager):
        """Defensive leave path clears player game association so the connection can rejoin."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")
        conn._outbox.clear()

        # simulate game mapping disappearing
        manager._games.pop("game1", None)

        await manager.leave_game(conn)

        # player state should be cleared so they can join another game
        player = manager._players.get(conn.connection_id)
        assert player is not None
        assert player.game_id is None
        assert player.seat is None

        # verify the player can now join a different game on the same connection
        manager.create_game("game2")
        await manager.join_game(conn, "game2", "Alice")

        game_joined = conn.sent_messages[0]
        assert game_joined["type"] == SessionMessageType.GAME_JOINED
        assert game_joined["game_id"] == "game2"


class TestSessionCleanup:
    async def test_game_cleanup_removes_all_sessions(self, manager):
        """When the last player leaves and game is cleaned up, all sessions are removed."""
        conn1 = MockConnection()
        conn2 = MockConnection()
        manager.register_connection(conn1)
        manager.register_connection(conn2)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conn1, "game1", "Alice")
        token1 = conn1.sent_messages[0]["session_token"]
        await manager.join_game(conn2, "game1", "Bob")
        token2 = conn2.sent_messages[0]["session_token"]

        # both leave, triggering cleanup
        await manager.leave_game(conn1)
        await manager.leave_game(conn2)

        assert manager._session_store.get_session(token1) is None
        assert manager._session_store.get_session(token2) is None
        assert manager.get_game("game1") is None


class TestInvalidActionSessionTracking:
    async def test_invalid_action_marks_session_disconnected(self, manager):
        """_handle_invalid_action marks the offender's session as disconnected."""
        conn = MockConnection()
        manager.register_connection(conn)
        game_obj = manager.create_game("game1")
        game_obj.started = True

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

        session_after = manager._session_store.get_session(session.session_token)
        assert session_after is not None
        assert session_after.disconnected_at is not None
