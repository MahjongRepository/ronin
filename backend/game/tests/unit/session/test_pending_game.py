"""Tests for pending game management (direct game creation from lobby).

Covers create_pending_game, join_game, timeout behavior, disconnect handling,
and the POST /games endpoint validation.
"""

import asyncio

import pytest
from starlette.testclient import TestClient

from game.logic.enums import WireClientMessageType
from game.messaging.encoder import decode, encode
from game.messaging.router import MessageRouter
from game.messaging.types import SessionErrorCode
from game.server.app import create_app
from game.server.types import CreateGameRequest, PlayerSpec
from game.session.manager import SessionManager
from game.session.models import Player
from game.tests.helpers.auth import TEST_TICKET_SECRET, make_test_game_ticket
from game.tests.mocks import MockConnection, MockGameService


def _make_specs(count: int = 1) -> list[PlayerSpec]:
    """Create a list of PlayerSpec objects for testing."""
    return [
        PlayerSpec(
            name=f"Player{i}",
            user_id=f"user-{i}",
            game_ticket=f"ticket-{i}",
        )
        for i in range(count)
    ]


def _error_messages(conn: MockConnection) -> list[dict]:
    """Extract error messages from a connection's outbox."""
    return [m for m in conn.sent_messages if m.get("type") == "session_error"]


def _error_codes(conn: MockConnection) -> list[str]:
    """Extract error codes from a connection's outbox."""
    return [m["code"] for m in _error_messages(conn)]


class TestCreatePendingGame:
    @pytest.fixture
    def manager(self):
        return SessionManager(MockGameService())

    async def test_creates_game_and_sessions(self, manager: SessionManager):
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        assert manager.get_game("game1") is not None
        assert "game1" in manager._pending_games
        assert manager.pending_game_count == 1

        # Session created with game_ticket as token
        session = manager._session_store.get_session("ticket-0")
        assert session is not None
        assert session.player_name == "Player0"
        assert session.game_id == "game1"

    async def test_rejects_duplicate_game_id(self, manager: SessionManager):
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        with pytest.raises(ValueError, match="already exists"):
            manager.create_pending_game("game1", _make_specs(1), num_ai_players=3)


class TestJoinGame:
    @pytest.fixture
    def manager(self):
        return SessionManager(MockGameService())

    async def test_join_game_starts_game_when_all_connected(self, manager: SessionManager):
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", "ticket-0")

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True
        assert "game1" not in manager._pending_games

    async def test_join_game_with_invalid_session_token(self, manager: SessionManager):
        manager.create_pending_game("game1", _make_specs(1), num_ai_players=3)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", "invalid-ticket")

        assert SessionErrorCode.JOIN_GAME_NO_SESSION in _error_codes(conn)

    async def test_join_game_nonexistent_game(self, manager: SessionManager):
        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "nonexistent", "ticket-0")

        assert SessionErrorCode.JOIN_GAME_NOT_FOUND in _error_codes(conn)

    async def test_join_game_already_started(self, manager: SessionManager):
        """After game starts, JOIN_GAME should return ALREADY_STARTED error."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        conn1 = MockConnection()
        manager.register_connection(conn1)
        await manager.join_game(conn1, "game1", "ticket-0")
        assert manager.get_game("game1").started is True

        conn2 = MockConnection()
        manager.register_connection(conn2)
        await manager.join_game(conn2, "game1", "ticket-0")

        assert SessionErrorCode.JOIN_GAME_ALREADY_STARTED in _error_codes(conn2)

    async def test_join_game_connection_already_in_game(self, manager: SessionManager):
        """A connection already in a game cannot join another via JOIN_GAME."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", "ticket-0")

        # Same connection tries with a different ticket
        await manager.join_game(conn, "game1", "ticket-1")
        assert SessionErrorCode.ALREADY_IN_GAME in _error_codes(conn)

    async def test_join_game_game_id_mismatch(self, manager: SessionManager):
        """Session token for a different game should be rejected."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        specs2 = [PlayerSpec(name="OtherPlayer", user_id="other", game_ticket="other-ticket")]
        manager.create_pending_game("game2", specs2, num_ai_players=3)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game2", "ticket-0")

        assert SessionErrorCode.RECONNECT_GAME_MISMATCH in _error_codes(conn)

    async def test_join_game_evicts_stale_connection_on_duplicate_token(self, manager: SessionManager):
        """Duplicate JOIN_GAME with same session_token evicts the old connection."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn1 = MockConnection()
        manager.register_connection(conn1)
        await manager.join_game(conn1, "game1", "ticket-0")

        # Same token via different connection — old connection should be evicted
        conn2 = MockConnection()
        manager.register_connection(conn2)
        await manager.join_game(conn2, "game1", "ticket-0")

        assert len(_error_messages(conn2)) == 0

        pending = manager._pending_games.get("game1")
        assert pending is not None
        # connected_count stays at 1 (replacement, not new player)
        assert pending.connected_count == 1

        # New connection is registered, old one is removed from the game
        game = manager._games["game1"]
        assert conn2.connection_id in game.players
        assert conn1.connection_id not in game.players

        # Stale connection is removed from _connections and closed
        assert conn1.connection_id not in manager._connections
        assert conn1.is_closed

        # Heartbeat tracking is cleaned up for the old connection
        assert conn1.connection_id not in manager._heartbeat._last_ping

    async def test_join_game_multi_player(self, manager: SessionManager):
        """Multiple players joining a 2-player game triggers game start."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn1 = MockConnection()
        manager.register_connection(conn1)
        await manager.join_game(conn1, "game1", "ticket-0")

        assert "game1" in manager._pending_games

        conn2 = MockConnection()
        manager.register_connection(conn2)
        await manager.join_game(conn2, "game1", "ticket-1")

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True
        assert "game1" not in manager._pending_games


class TestPendingGameTimeout:
    @pytest.fixture
    def manager(self):
        return SessionManager(MockGameService())

    async def test_timeout_starts_game_with_ai_substitutes(self, manager: SessionManager):
        """After timeout, game starts with AI substitutes for missing players."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", "ticket-0")

        pending = manager._pending_games.get("game1")
        assert pending is not None
        assert pending.timeout_task is not None

        # Cancel the real timeout and trigger manually with a short duration
        pending.timeout_task.cancel()
        await manager._pending_game_timeout("game1", 0)

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True
        assert "game1" not in manager._pending_games

    async def test_timeout_cancelled_when_all_players_connect(self, manager: SessionManager):
        """Timeout task is cancelled when all expected players connect."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        pending = manager._pending_games.get("game1")
        timeout_task = pending.timeout_task
        assert timeout_task is not None

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", "ticket-0")

        # Let the event loop process the cancellation
        await asyncio.sleep(0)
        assert timeout_task.done()

    async def test_timeout_with_no_players_connected_cancels_game(self, manager: SessionManager):
        """Timeout with zero players connected cancels game instead of starting."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        # Cancel the real timeout and trigger manually with a short duration
        pending = manager._pending_games.get("game1")
        assert pending is not None
        assert pending.timeout_task is not None
        pending.timeout_task.cancel()
        await manager._pending_game_timeout("game1", 0)

        # Game should be cleaned up, not started
        assert manager.get_game("game1") is None
        assert "game1" not in manager._pending_games

        # Sessions should be cleaned up
        session = manager._session_store.get_session("ticket-0")
        assert session is None


class TestPendingGameDisconnect:
    @pytest.fixture
    def manager(self):
        return SessionManager(MockGameService())

    async def test_disconnect_marks_session_disconnected(self, manager: SessionManager):
        """Disconnecting during pending phase marks session disconnected, not removed."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", "ticket-0")

        await manager.leave_game(conn, notify_player=False)

        session = manager._session_store.get_session("ticket-0")
        assert session is not None
        assert session.disconnected_at is not None

    async def test_disconnect_and_reconnect_during_pending(self, manager: SessionManager):
        """Player can disconnect and rejoin during pending window with same ticket."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn1 = MockConnection()
        manager.register_connection(conn1)
        await manager.join_game(conn1, "game1", "ticket-0")

        await manager.leave_game(conn1, notify_player=False)
        manager.unregister_connection(conn1)

        conn2 = MockConnection()
        manager.register_connection(conn2)
        await manager.join_game(conn2, "game1", "ticket-0")

        assert len(_error_messages(conn2)) == 0

        pending = manager._pending_games.get("game1")
        assert pending is not None
        assert pending.connected_count == 1

    async def test_pending_game_survives_empty(self, manager: SessionManager):
        """Pending game is not cleaned up when all players disconnect (timeout handles it)."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", "ticket-0")

        await manager.leave_game(conn, notify_player=False)
        manager.unregister_connection(conn)

        # Game should still exist (pending, waiting for timeout)
        assert manager.get_game("game1") is not None
        assert "game1" in manager._pending_games

    async def test_cleanup_after_timeout_start(self, manager: SessionManager):
        """After timeout starts the game, cleanup happens normally on disconnect."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", "ticket-0")

        # Game started immediately (only 1 player expected)
        assert manager.get_game("game1").started is True
        assert "game1" not in manager._pending_games

        # Disconnect from started game - should clean up
        await manager.leave_game(conn, notify_player=False)
        manager.unregister_connection(conn)

        assert manager.get_game("game1") is None


class TestCreateGameRequestValidation:
    def test_player_count_mismatch(self):
        with pytest.raises(ValueError, match="Expected 1 players"):
            CreateGameRequest(
                game_id="test-game",
                num_ai_players=3,
                players=[
                    PlayerSpec(name="Alice", user_id="u1", game_ticket="t1"),
                    PlayerSpec(name="Bob", user_id="u2", game_ticket="t2"),
                ],
            )

    def test_duplicate_game_tickets(self):
        with pytest.raises(ValueError, match="Duplicate game_ticket"):
            CreateGameRequest(
                game_id="test-game",
                num_ai_players=2,
                players=[
                    PlayerSpec(name="Alice", user_id="u1", game_ticket="same-ticket"),
                    PlayerSpec(name="Bob", user_id="u2", game_ticket="same-ticket"),
                ],
            )

    def test_duplicate_names(self):
        with pytest.raises(ValueError, match="Duplicate player name"):
            CreateGameRequest(
                game_id="test-game",
                num_ai_players=2,
                players=[
                    PlayerSpec(name="Alice", user_id="u1", game_ticket="t1"),
                    PlayerSpec(name="Alice", user_id="u2", game_ticket="t2"),
                ],
            )

    def test_duplicate_user_ids(self):
        with pytest.raises(ValueError, match="Duplicate user_id"):
            CreateGameRequest(
                game_id="test-game",
                num_ai_players=2,
                players=[
                    PlayerSpec(name="Alice", user_id="same-id", game_ticket="t1"),
                    PlayerSpec(name="Bob", user_id="same-id", game_ticket="t2"),
                ],
            )


class TestPostGamesEndpoint:
    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    @staticmethod
    def _signed_player(name: str, user_id: str, game_id: str) -> dict:
        """Build a player dict with a valid signed game ticket."""
        ticket = make_test_game_ticket(name, game_id, user_id=user_id)
        return {"name": name, "user_id": user_id, "game_ticket": ticket}

    def test_create_game_success(self, client):
        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [self._signed_player("Alice", "u1", "test-game")],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["game_id"] == "test-game"
        assert data["status"] == "pending"

    def test_create_game_invalid_body(self, client):
        response = client.post("/games", content=b"not json")
        assert response.status_code == 400

    def test_create_game_duplicate_id(self, client):
        # Create game first via endpoint
        client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [self._signed_player("Alice", "u1", "test-game")],
            },
        )
        # Duplicate
        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [self._signed_player("Bob", "u2", "test-game")],
            },
        )
        assert response.status_code == 409

    def test_create_game_at_capacity(self, client):
        client.app.state.settings.max_capacity = 1

        response = client.post(
            "/games",
            json={
                "game_id": "game1",
                "num_ai_players": 3,
                "players": [self._signed_player("Alice", "u1", "game1")],
            },
        )
        assert response.status_code == 201

        response = client.post(
            "/games",
            json={
                "game_id": "game2",
                "num_ai_players": 3,
                "players": [self._signed_player("Bob", "u2", "game2")],
            },
        )
        assert response.status_code == 503

    def test_create_game_body_too_large(self, client):
        response = client.post("/games", content=b"x" * 5000)
        assert response.status_code == 413

    def test_create_game_invalid_ticket(self, client):
        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [{"name": "Alice", "user_id": "u1", "game_ticket": "invalid-ticket"}],
            },
        )
        assert response.status_code == 400
        assert "Invalid or expired game ticket" in response.json()["error"]

    def test_create_game_ticket_game_id_mismatch(self, client):
        ticket = make_test_game_ticket("Alice", "other-game", user_id="u1")
        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [{"name": "Alice", "user_id": "u1", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 400
        assert "game_id mismatch" in response.json()["error"]

    def test_create_game_ticket_identity_mismatch(self, client):
        ticket = make_test_game_ticket("Alice", "test-game", user_id="u1")
        response = client.post(
            "/games",
            json={
                "game_id": "test-game",
                "num_ai_players": 3,
                "players": [{"name": "FakeAlice", "user_id": "u1", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 400
        assert "identity mismatch" in response.json()["error"]


class TestJoinGameViaRouter:
    """Test JOIN_GAME routing through MessageRouter."""

    @pytest.fixture
    def manager(self):
        return SessionManager(MockGameService())

    @pytest.fixture
    def router(self, manager):
        return MessageRouter(manager, game_ticket_secret=TEST_TICKET_SECRET)

    async def test_join_game_via_router(self, manager, router):
        game_id = "test-game"
        ticket = make_test_game_ticket("Alice", game_id, user_id="alice-id")

        specs = [PlayerSpec(name="Alice", user_id="alice-id", game_ticket=ticket)]
        manager.create_pending_game(game_id, specs, num_ai_players=3)

        conn = MockConnection(game_id=game_id)
        await router.handle_connect(conn)

        await router.handle_message(
            conn,
            {
                "t": WireClientMessageType.JOIN_GAME,
                "game_ticket": ticket,
            },
        )

        game = manager.get_game(game_id)
        assert game is not None
        assert game.started is True

    async def test_join_game_invalid_ticket_via_router(self, manager, router):
        game_id = "test-game"
        specs = [PlayerSpec(name="Alice", user_id="alice-id", game_ticket="valid-ticket")]
        manager.create_pending_game(game_id, specs, num_ai_players=3)

        conn = MockConnection(game_id=game_id)
        await router.handle_connect(conn)

        await router.handle_message(
            conn,
            {
                "t": WireClientMessageType.JOIN_GAME,
                "game_ticket": "forged-ticket",
            },
        )

        # Should get INVALID_TICKET error (signature verification fails)
        assert SessionErrorCode.INVALID_TICKET in _error_codes(conn)


class TestJoinGameViaWebSocket:
    """Integration test for JOIN_GAME via WebSocket (game_id from connection)."""

    @pytest.fixture
    def client(self):
        app = create_app(game_service=MockGameService())
        return TestClient(app)

    def test_join_game_uses_connection_game_id(self, client):
        game_id = "ws-game"
        ticket = make_test_game_ticket("Alice", game_id, user_id="alice-id")

        # Create pending game via POST
        response = client.post(
            "/games",
            json={
                "game_id": game_id,
                "num_ai_players": 3,
                "players": [{"name": "Alice", "user_id": "alice-id", "game_ticket": ticket}],
            },
        )
        assert response.status_code == 201

        # Connect via WebSocket and send JOIN_GAME (game_id from URL path)
        with client.websocket_connect(f"/ws/{game_id}") as ws:
            ws.send_bytes(
                encode(
                    {
                        "t": WireClientMessageType.JOIN_GAME,
                        "game_ticket": ticket,
                    },
                ),
            )

            # Should receive game events (game started)
            msg = decode(ws.receive_bytes())
            assert msg is not None


class TestPendingGameDefensivePaths:
    """Tests for defensive code paths in pending game management."""

    @pytest.fixture
    def manager(self):
        return SessionManager(MockGameService())

    async def test_leave_pending_game_without_pending_info(self, manager: SessionManager):
        """Exercise _leave_pending_game fallback when pending info is gone."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn = MockConnection()
        manager.register_connection(conn)
        await manager.join_game(conn, "game1", "ticket-0")

        # Game should still be pending (only 1 of 2 connected)
        assert "game1" in manager._pending_games

        # Manually remove the pending info to exercise the fallback path
        pending = manager._pending_games.pop("game1", None)
        if pending and pending.timeout_task:
            pending.timeout_task.cancel()

        # This should fall through to the no-pending-info path in _leave_pending_game
        await manager.leave_game(conn, notify_player=False)

    async def test_complete_pending_game_when_already_popped(self, manager: SessionManager):
        """_complete_pending_game is a no-op if pending was already popped."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        pending = manager._pending_games.get("game1")
        assert pending is not None

        # Manually pop the pending info
        manager._pending_games.pop("game1", None)

        # Lock survives because we hold a reference to pending
        async with pending.lock:
            await manager._complete_pending_game("game1")

        # Should be a no-op, game still not started
        game = manager.get_game("game1")
        assert game is not None
        assert game.started is False

    async def test_complete_pending_game_when_game_gone(self, manager: SessionManager):
        """_complete_pending_game handles game being removed from _games."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        pending = manager._pending_games.get("game1")
        assert pending is not None

        # Manually remove the game (simulate race condition)
        manager._games.pop("game1", None)

        async with pending.lock:
            await manager._complete_pending_game("game1")

        # Should be a no-op
        assert "game1" not in manager._pending_games

    async def test_pending_game_timeout_when_pending_gone(self, manager: SessionManager):
        """_pending_game_timeout is a no-op when pending info is already removed."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        # Cancel the real timeout and manually remove pending info
        pending = manager._pending_games.get("game1")
        if pending and pending.timeout_task:
            pending.timeout_task.cancel()

        manager._pending_games.pop("game1", None)

        # Manually call the timeout - should be a no-op since pending is gone
        await manager._pending_game_timeout("game1", 0)

    async def test_validate_join_game_game_started_in_lock(self, manager: SessionManager):
        """_validate_join_game handles game.started race inside the lock."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn = MockConnection()
        manager.register_connection(conn)

        # Manually set game as started to simulate race
        game = manager.get_game("game1")
        assert game is not None
        game.started = True

        result = manager._validate_join_game(conn.connection_id, "game1", "ticket-0")
        assert result is not None
        assert result[0] == SessionErrorCode.JOIN_GAME_ALREADY_STARTED

    async def test_cleanup_empty_game_with_pending_timeout(self, manager: SessionManager):
        """_cleanup_empty_game cancels pending timeout when game becomes empty."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        # Simulate: game started but pending state still lingering (shouldn't happen
        # normally, but _cleanup_empty_game defensively handles it)
        game = manager.get_game("game1")
        assert game is not None
        game.started = True

        # Manually add a player to make it non-empty, then remove to trigger cleanup
        conn = MockConnection()
        manager.register_connection(conn)
        player = Player(connection=conn, name="P", session_token="tok", game_id="game1")
        manager._players[conn.connection_id] = player
        game.players[conn.connection_id] = player

        # Now remove player (makes game empty) and run cleanup
        game.players.pop(conn.connection_id)
        assert game.is_empty
        await manager._cleanup_empty_game("game1", game)

        assert "game1" not in manager._pending_games

    async def test_validate_join_game_game_removed_from_games(self, manager: SessionManager):
        """_validate_join_game returns NOT_FOUND when game removed from _games inside lock."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        conn = MockConnection()
        manager.register_connection(conn)

        # Remove game from _games to simulate race
        manager._games.pop("game1", None)

        result = manager._validate_join_game(conn.connection_id, "game1", "ticket-0")
        assert result is not None
        assert result[0] == SessionErrorCode.JOIN_GAME_NOT_FOUND

    async def test_register_pending_player_guard_clauses(self, manager: SessionManager):
        """_register_pending_player is a no-op if game/pending/session are gone."""
        specs = _make_specs(1)
        manager.create_pending_game("game1", specs, num_ai_players=3)

        conn = MockConnection()
        manager.register_connection(conn)

        # Remove game from _games to trigger the guard
        manager._games.pop("game1", None)

        await manager._register_pending_player(conn, "game1", "ticket-0")

    async def test_evicted_connection_rejected_on_rejoin(self, manager: SessionManager):
        """An evicted connection (removed from _connections) cannot re-JOIN_GAME."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn1 = MockConnection()
        manager.register_connection(conn1)
        await manager.join_game(conn1, "game1", "ticket-0")

        # conn2 joins with the same token, evicting conn1
        conn2 = MockConnection()
        manager.register_connection(conn2)
        await manager.join_game(conn2, "game1", "ticket-0")

        # conn1 has been evicted: removed from _connections
        assert conn1.connection_id not in manager._connections

        # conn1 tries to JOIN_GAME again (stale message loop still running).
        # The call is silently ignored because conn1 is no longer registered.
        await manager.join_game(conn1, "game1", "ticket-0")

        # conn2 must still be the active player, not evicted by conn1
        game = manager._games["game1"]
        assert conn2.connection_id in game.players
        assert conn1.connection_id not in game.players

    async def test_leave_pending_game_skips_evicted_player_with_lock(self, manager: SessionManager):
        """_leave_pending_game is a no-op when the player was already evicted by a duplicate JOIN_GAME."""
        specs = _make_specs(2)
        manager.create_pending_game("game1", specs, num_ai_players=2)

        conn1 = MockConnection()
        manager.register_connection(conn1)
        await manager.join_game(conn1, "game1", "ticket-0")

        pending = manager._pending_games.get("game1")
        assert pending is not None
        assert pending.connected_count == 1

        # Simulate the state left by a concurrent JOIN_GAME eviction:
        # the eviction removed the player from _players and game.players,
        # set player.game_id = None, and called mark_reconnected.
        player = manager._players[conn1.connection_id]
        game = manager._games["game1"]
        game.players.pop(conn1.connection_id)
        manager._players.pop(conn1.connection_id)
        player.game_id = None
        manager._session_store.mark_reconnected("ticket-0")

        # Call _leave_pending_game directly (as leave_game would after
        # reading the stale player reference before the lock)
        await manager._leave_pending_game(game, conn1, player, notify_player=False)

        # connected_count must NOT be decremented (eviction didn't increment)
        assert pending.connected_count == 1
        # Session must still be marked as connected (not overwritten to disconnected)
        session = manager._session_store.get_session("ticket-0")
        assert session is not None
        assert session.disconnected_at is None
