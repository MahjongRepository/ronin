"""Integration tests for matchmaking WebSocket handler."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketState

from lobby.matchmaking.models import QueueEntry
from lobby.server.app import create_app
from lobby.server.settings import LobbyServerSettings
from lobby.tests.integration.conftest import register_with_csrf
from shared.auth.settings import AuthSettings


def _make_app(tmp_path, **settings_kwargs):
    config_file = tmp_path / "servers.yaml"
    config_file.write_text("""
servers:
  - name: "test-server"
    url: "http://localhost:8711"
    client_url: "http://localhost:8711"
""")
    static_dir = tmp_path / "public"
    (static_dir / "styles").mkdir(parents=True)
    (static_dir / "styles" / "lobby.css").write_text("/* test */")
    settings_kwargs.setdefault("ws_allowed_origin", None)
    return create_app(
        settings=LobbyServerSettings(
            config_path=config_file,
            static_dir=str(static_dir),
            **settings_kwargs,
        ),
        auth_settings=AuthSettings(
            game_ticket_secret="test-secret",
            database_path=str(tmp_path / "test.db"),
            cookie_secure=False,
        ),
    )


def _make_mock_entry(user_id: str, username: str, connection_id: str) -> QueueEntry:
    """Create a mock QueueEntry with a fake websocket for testing."""
    ws = MagicMock()
    ws.client_state = WebSocketState.CONNECTED
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return QueueEntry(
        connection_id=connection_id,
        user_id=user_id,
        username=username,
        websocket=ws,
    )


class TestMatchmakingWebSocket:
    @pytest.fixture
    def app(self, tmp_path):
        app = _make_app(tmp_path)
        yield app
        app.state.db.close()

    @pytest.fixture
    def client(self, app):
        c = TestClient(app)
        register_with_csrf(c, "player1")
        return c

    def test_connect_and_join_queue(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "queue_joined"
            assert msg["queue_size"] == 1
            assert msg["position"] == 1

    def test_ping_pong(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            ws.receive_json()  # queue_joined
            ws.send_text(json.dumps({"type": "ping"}))
            msg = ws.receive_json()
            assert msg["type"] == "pong"

    def test_invalid_message(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            ws.receive_json()  # queue_joined
            ws.send_text("not json")
            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_unknown_message_type_rejected(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            ws.receive_json()  # queue_joined
            ws.send_text(json.dumps({"type": "unknown"}))
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "Invalid message format"

    def test_oversized_message_rejected(self, client):
        with client.websocket_connect("/ws/matchmaking") as ws:
            ws.receive_json()  # queue_joined
            big = json.dumps({"type": "ping", "padding": "x" * 5000})
            ws.send_text(big)
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "too large" in msg["message"].lower()

    def test_disconnect_removes_from_queue(self, app, client):
        with client.websocket_connect("/ws/matchmaking"):
            assert app.state.matchmaking_manager.queue_size == 1
        assert app.state.matchmaking_manager.queue_size == 0

    def test_already_in_queue_rejected(self, app, client):
        """Second matchmaking connection from same user gets already_in_queue error."""
        with (
            patch.object(
                app.state.matchmaking_manager,
                "add_player",
                side_effect=ValueError("already_in_queue"),
            ),
            client.websocket_connect("/ws/matchmaking") as ws,
        ):
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "already_in_queue"

    def test_already_in_room_rejected(self, app, client):
        room = app.state.room_manager.create_room("test-room")
        # Join the room first
        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_room:
            ws_room.receive_json()  # room_joined
            # Now try matchmaking
            with client.websocket_connect("/ws/matchmaking") as ws_mm:
                msg = ws_mm.receive_json()
                assert msg["type"] == "error"
                assert msg["message"] == "already_in_room"


class TestMatchmakingUnauthenticated:
    @pytest.fixture
    def unauthenticated_client(self, tmp_path):
        app = _make_app(tmp_path)
        c = TestClient(app)
        yield c
        app.state.db.close()

    def test_unauthenticated_ws_rejected(self, unauthenticated_client):
        with (
            pytest.raises(Exception),  # noqa: B017, PT011
            unauthenticated_client.websocket_connect("/ws/matchmaking") as ws,
        ):
            ws.receive_json()


class TestMatchmakingOriginCheck:
    @pytest.fixture
    def app_with_origin(self, tmp_path):
        app = _make_app(tmp_path, ws_allowed_origin="http://localhost:3000")
        yield app
        app.state.db.close()

    @pytest.fixture
    def client_with_origin(self, app_with_origin):
        c = TestClient(app_with_origin)
        register_with_csrf(c, "player1")
        return c

    def test_allowed_origin_connects(self, client_with_origin):
        with client_with_origin.websocket_connect(
            "/ws/matchmaking",
            headers={"origin": "http://localhost:3000"},
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "queue_joined"

    def test_forbidden_origin_rejected(self, client_with_origin):
        with (
            pytest.raises(Exception),  # noqa: B017, PT011
            client_with_origin.websocket_connect(
                "/ws/matchmaking",
                headers={"origin": "http://evil.com"},
            ) as ws,
        ):
            ws.receive_json()


class TestMatchmakingGameTransition:
    """Tests for matchmaking triggering game creation when 4 players match.

    Pre-populates the queue with 3 mock entries, then connects the 4th player
    via a real WebSocket. This avoids threading issues from multiple concurrent
    TestClient WebSocket connections.
    """

    @pytest.fixture
    def app(self, tmp_path):
        app = _make_app(tmp_path)
        yield app
        app.state.db.close()

    @pytest.fixture
    def client(self, app):
        c = TestClient(app)
        register_with_csrf(c, "player4")
        return c

    def _set_servers_healthy(self, app):
        for server in app.state.registry._servers:
            server.healthy = True

    def _prefill_queue(self, app, count=3):
        """Add mock players to the queue so the next real connection triggers a match."""
        mgr = app.state.matchmaking_manager
        entries = []
        for i in range(count):
            entry = _make_mock_entry(f"fake-uid-{i}", f"fake-player-{i}", f"fake-conn-{i}")
            mgr.add_player(entry)
            entries.append(entry)
        return entries

    def test_fourth_player_triggers_game_starting(self, app, client):
        """When 4th player connects, they receive game_starting and mock players get notified."""
        self._set_servers_healthy(app)
        mock_entries = self._prefill_queue(app, 3)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.text = ""

        with (
            patch.object(app.state.registry, "check_health", new_callable=AsyncMock),
            patch("lobby.game_transition.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with client.websocket_connect("/ws/matchmaking") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "game_starting"
                assert "ws_url" in msg
                assert "game_ticket" in msg
                assert "game_id" in msg

        # Mock players should have received game_starting too
        for entry in mock_entries:
            entry.websocket.send_json.assert_called_once()
            call_args = entry.websocket.send_json.call_args[0][0]
            assert call_args["type"] == "game_starting"
            assert "ws_url" in call_args
            assert "game_ticket" in call_args

        # Queue should be empty
        assert app.state.matchmaking_manager.queue_size == 0

    def test_game_server_failure_requeues_players(self, app, client):
        """When game server fails, matched players are re-queued."""
        self._set_servers_healthy(app)
        self._prefill_queue(app, 3)

        with (
            patch.object(app.state.registry, "check_health", new_callable=AsyncMock),
            patch("lobby.game_transition.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused"),
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with client.websocket_connect("/ws/matchmaking") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "Failed to start game" in msg["message"]

        # 3 mock players re-queued; the real client disconnected and was cleaned up
        assert app.state.matchmaking_manager.queue_size == 3

    def test_disconnected_player_requeues_remaining(self, app, client):
        """When a matched player disconnected before game creation, remaining are re-queued."""
        self._set_servers_healthy(app)
        mgr = app.state.matchmaking_manager

        # Add 2 connected mock entries
        connected_entries = []
        for i in range(2):
            entry = _make_mock_entry(f"fake-uid-{i}", f"fake-player-{i}", f"fake-conn-{i}")
            mgr.add_player(entry)
            connected_entries.append(entry)

        # Add 1 disconnected mock entry
        disc_entry = _make_mock_entry("fake-uid-disc", "disc-player", "fake-conn-disc")
        disc_entry.websocket.client_state = WebSocketState.DISCONNECTED
        mgr.add_player(disc_entry)

        # 4th player connects, triggering match but finding a disconnected player
        with client.websocket_connect("/ws/matchmaking") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "queue_update"

        # Connected mock entries should have been re-queued
        for entry in connected_entries:
            assert mgr.has_user(entry.user_id)
        # Disconnected player should NOT have been re-queued
        assert not mgr.has_user("fake-uid-disc")
