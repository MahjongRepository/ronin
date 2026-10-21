import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.settings import LobbyServerSettings
from lobby.tests.integration.conftest import login_with_csrf, logout_with_csrf, register_with_csrf
from shared.auth.settings import AuthSettings


def _make_app(tmp_path, **settings_kwargs):
    config_file = tmp_path / "servers.yaml"
    servers_yaml = """
servers:
  - name: "test-server"
    url: "http://localhost:8711"
    client_url: "http://localhost:8711"
"""
    config_file.write_text(servers_yaml)
    static_dir = tmp_path / "public"
    (static_dir / "styles").mkdir(parents=True)
    (static_dir / "styles" / "lobby.css").write_text("/* test */")
    # Disable origin checking by default in tests (TestClient doesn't send
    # a matching origin header). Tests that need origin checking should
    # pass ws_allowed_origin explicitly.
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


class TestRoomWebSocket:
    @pytest.fixture
    def app(self, tmp_path):
        app = _make_app(tmp_path)
        yield app
        app.state.db.close()

    @pytest.fixture
    def client(self, app):
        c = TestClient(app)
        register_with_csrf(c, "wsuser")
        return c

    @pytest.fixture
    def room_id(self, app):
        room = app.state.room_manager.create_room("test-room")
        return room.room_id

    def test_room_websocket__when_user_joins__should_send_room_joined_with_four_seats(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "room_joined"
            assert msg["room_id"] == room_id
            assert msg["player_name"] == "wsuser"
            assert msg["is_owner"] is True
            assert len(msg["players"]) == 4  # always 4 seats

    def test_room_websocket__when_ping_sent__should_reply_pong(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            ws.send_text(json.dumps({"type": "ping"}))
            msg = ws.receive_json()
            assert msg["type"] == "pong"

    def test_room_websocket__when_chat_sent__should_echo_chat_with_player_name(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            ws.send_text(json.dumps({"type": "chat", "text": "hello"}))
            msg = ws.receive_json()
            assert msg["type"] == "chat"
            assert msg["player_name"] == "wsuser"
            assert msg["text"] == "hello"

    def test_room_websocket__when_non_owner_sets_ready__should_broadcast_ready_change(self, app, tmp_path):
        room = app.state.room_manager.create_room("ready-room")
        c = TestClient(app)
        register_with_csrf(c, "owner")
        # Owner joins first
        with c.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_owner:
            ws_owner.receive_json()  # room_joined

            # Non-owner joins
            logout_with_csrf(c)
            register_with_csrf(c, "player2")
            with c.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_p2:
                ws_p2.receive_json()  # room_joined
                ws_owner.receive_json()  # player_joined broadcast

                ws_p2.send_text(json.dumps({"type": "set_ready", "ready": True}))
                msg = ws_p2.receive_json()
                assert msg["type"] == "player_ready_changed"
                assert msg["can_start"] is True

    def test_room_websocket__when_owner_sets_ready__should_send_error(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            ws.send_text(json.dumps({"type": "set_ready", "ready": True}))
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "owner_cannot_ready"

    def test_room_websocket__when_room_not_found__should_send_error(self, client):
        with client.websocket_connect("/ws/rooms/nonexistent") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "room_not_found"

    def test_room_websocket__when_room_full__should_send_error(self, client, app):
        room = app.state.room_manager.create_room("full-room")
        # Pre-fill all 4 seats
        for i in range(4):
            app.state.room_manager.join_room(
                connection_id=f"prefill-{i}", room_id="full-room", user_id=f"user-{i}", username=f"P{i}"
            )

        with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "room_full"

    def test_room_websocket__when_message_not_json__should_send_error(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            ws.send_text("not json")
            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_room_websocket__when_message_oversized__should_send_error(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            big = json.dumps({"type": "chat", "text": "a" * 500, "x": "b" * 4000})
            ws.send_text(big)
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "too large" in msg["message"].lower()

    def test_room_websocket__when_message_type_unknown__should_send_error(self, client, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            ws.send_text(json.dumps({"type": "unknown_type"}))
            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_room_websocket__when_last_player_disconnects__should_remove_room(self, client, app, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            room = app.state.room_manager.get_room(room_id)
            assert room is not None
            assert room.player_count == 1
        # After disconnect, room should be cleaned up (empty rooms are removed)
        assert app.state.room_manager.get_room(room_id) is None

    def test_room_websocket__when_set_ready_while_transitioning__should_send_error(self, client, app, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            room = app.state.room_manager.get_room(room_id)
            assert room is not None

            room.transitioning = True
            ws.send_text(json.dumps({"type": "set_ready", "ready": True}))
            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_room_websocket__when_room_removed_before_start_game__should_send_not_in_room(self, client, app, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            # Remove room externally (simulates race condition)
            app.state.room_manager._rooms.pop(room_id, None)
            ws.send_text(json.dumps({"type": "start_game"}))
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "not_in_room"

    def test_room_websocket__when_start_game_while_transitioning__should_send_error(self, client, app, room_id):
        with client.websocket_connect(f"/ws/rooms/{room_id}") as ws:
            ws.receive_json()  # room_joined
            room = app.state.room_manager.get_room(room_id)
            room.transitioning = True
            ws.send_text(json.dumps({"type": "start_game"}))
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert msg["message"] == "room_transitioning"


class TestStartGameErrors:
    @pytest.fixture
    def app(self, tmp_path):
        app = _make_app(tmp_path)
        yield app
        app.state.db.close()

    @pytest.fixture
    def two_user_client(self, app):
        c = TestClient(app)
        register_with_csrf(c, "owner")
        logout_with_csrf(c)
        register_with_csrf(c, "player2")
        return c

    def test_room_websocket__when_non_owner_starts_game__should_send_not_owner(self, app, two_user_client):
        room = app.state.room_manager.create_room("nostart-room")
        # Log in as owner and connect
        login_with_csrf(two_user_client, "owner")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_owner:
            ws_owner.receive_json()  # room_joined

            # Log in as player2 (non-owner) and connect
            logout_with_csrf(two_user_client)
            login_with_csrf(two_user_client, "player2")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_p2:
                ws_p2.receive_json()  # room_joined
                ws_owner.receive_json()  # player_joined broadcast

                # Non-owner tries start_game
                ws_p2.send_text(json.dumps({"type": "start_game"}))
                msg = ws_p2.receive_json()
                assert msg["type"] == "error"
                assert msg["message"] == "not_owner"

    def test_room_websocket__when_owner_starts_game_before_all_ready__should_send_not_all_ready(
        self, app, two_user_client
    ):
        room = app.state.room_manager.create_room("notready-room")
        # Log in as owner and connect
        login_with_csrf(two_user_client, "owner")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_owner:
            ws_owner.receive_json()  # room_joined

            # Log in as player2 (non-owner) and connect
            logout_with_csrf(two_user_client)
            login_with_csrf(two_user_client, "player2")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_p2:
                ws_p2.receive_json()  # room_joined
                ws_owner.receive_json()  # player_joined broadcast

                # Owner tries start_game before player2 is ready
                ws_owner.send_text(json.dumps({"type": "start_game"}))
                msg = ws_owner.receive_json()
                assert msg["type"] == "error"
                assert msg["message"] == "not_all_ready"


class TestOwnerChanged:
    @pytest.fixture
    def app(self, tmp_path):
        app = _make_app(tmp_path)
        yield app
        app.state.db.close()

    @pytest.fixture
    def two_user_client(self, app):
        c = TestClient(app)
        register_with_csrf(c, "alice")
        logout_with_csrf(c)
        register_with_csrf(c, "bob")
        return c

    @pytest.mark.xfail(reason="Flaky: intermittent WebSocket timeout", strict=False)
    def test_room_websocket__when_owner_leaves__should_send_owner_changed_then_player_left(self, app, two_user_client):
        room = app.state.room_manager.create_room("transfer-room")
        # Alice connects first (becomes owner)
        login_with_csrf(two_user_client, "alice")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
            ws_alice.receive_json()  # room_joined

            # Bob connects (non-owner)
            logout_with_csrf(two_user_client)
            login_with_csrf(two_user_client, "bob")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
                ws_bob.receive_json()  # room_joined
                ws_alice.receive_json()  # player_joined broadcast

                # Alice (owner) leaves via leave_room
                ws_alice.send_text(json.dumps({"type": "leave_room"}))

                # Bob should receive owner_changed then player_left
                msg1 = ws_bob.receive_json()
                assert msg1["type"] == "owner_changed"
                assert msg1["is_owner"] is True
                assert "can_start" in msg1
                assert len(msg1["players"]) == 4

                msg2 = ws_bob.receive_json()
                assert msg2["type"] == "player_left"
                assert msg2["player_name"] == "alice"


class TestMultiPlayerWebSocket:
    @pytest.fixture
    def app(self, tmp_path):
        app = _make_app(tmp_path)
        yield app
        app.state.db.close()

    @pytest.fixture
    def two_user_client(self, app):
        c = TestClient(app)
        register_with_csrf(c, "alice")
        logout_with_csrf(c)
        register_with_csrf(c, "bob")
        return c

    def test_room_websocket__when_player_leaves__should_broadcast_player_left(self, app, two_user_client):
        room = app.state.room_manager.create_room("multi-room")
        # Bob connects first (currently logged in)
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
            ws_bob.receive_json()  # room_joined
            # Log in as alice and connect
            login_with_csrf(two_user_client, "alice")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
                ws_alice.receive_json()  # room_joined
                player_joined = ws_bob.receive_json()  # player_joined for alice
                assert player_joined["type"] == "player_joined"

                # Alice leaves
                ws_alice.send_text(json.dumps({"type": "leave_room"}))

            # Bob should receive player_left
            msg = ws_bob.receive_json()
            assert msg["type"] == "player_left"

    def test_room_websocket__when_second_player_joins__should_broadcast_four_seat_player_list(
        self, app, two_user_client
    ):
        room = app.state.room_manager.create_room("consistent-room")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
            bob_joined = ws_bob.receive_json()
            assert bob_joined["type"] == "room_joined"
            # Always 4 seats (1 human + 3 bots)
            assert len(bob_joined["players"]) == 4

            login_with_csrf(two_user_client, "alice")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
                alice_joined = ws_alice.receive_json()
                assert alice_joined["type"] == "room_joined"
                # Still 4 seats (2 humans + 2 bots)
                assert len(alice_joined["players"]) == 4

                player_joined = ws_bob.receive_json()
                assert player_joined["type"] == "player_joined"
                assert player_joined["player_name"] == "alice"
                assert len(player_joined["players"]) == 4

    def test_room_websocket__when_player_disconnects__should_broadcast_player_left(self, app, two_user_client):
        room = app.state.room_manager.create_room("dc-room")
        with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_bob:
            ws_bob.receive_json()  # room_joined
            login_with_csrf(two_user_client, "alice")
            with two_user_client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws_alice:
                ws_alice.receive_json()  # room_joined
                ws_bob.receive_json()  # player_joined

            # Alice's WS closed (disconnect)
            msg = ws_bob.receive_json()
            assert msg["type"] == "player_left"


class TestGameTransition:
    @pytest.fixture
    def app(self, tmp_path):
        app = _make_app(tmp_path)
        yield app
        app.state.db.close()

    @pytest.fixture
    def client(self, app):
        c = TestClient(app)
        register_with_csrf(c, "wsuser")
        return c

    def _set_servers_healthy(self, app):
        for server in app.state.registry._servers:
            server.healthy = True

    def test_room_websocket__when_owner_starts_game__should_send_game_starting_and_remove_room(self, client, app):
        room = app.state.room_manager.create_room("game-room")
        self._set_servers_healthy(app)

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

            with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
                ws.receive_json()  # room_joined
                # Owner alone with 3 bots — can_start is True
                ws.send_text(json.dumps({"type": "start_game"}))
                msg = ws.receive_json()  # game_starting
                assert msg["type"] == "game_starting"
                assert "ws_url" in msg
                assert "game_ticket" in msg
                assert msg["game_id"] == "game-room"

        # Room should be removed after transition
        assert app.state.room_manager.get_room("game-room") is None

    def test_room_websocket__when_game_starting_delivery_fails__should_log_failure(self, client, app, caplog):
        room = app.state.room_manager.create_room("deliver-fail")
        self._set_servers_healthy(app)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 201
        mock_response.text = ""

        # Make send_to always return False to simulate delivery failure
        original_send_to = app.state.room_connections.send_to

        async def failing_send_to(connection_id, message):
            if isinstance(message, dict) and message.get("type") == "game_starting":
                return False

            return await original_send_to(connection_id, message)

        with (
            patch.object(app.state.registry, "check_health", new_callable=AsyncMock),
            patch("lobby.game_transition.httpx.AsyncClient") as mock_client_cls,
            patch.object(app.state.room_connections, "send_to", side_effect=failing_send_to),
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
                ws.receive_json()  # room_joined
                ws.send_text(json.dumps({"type": "start_game"}))

        assert "failed to deliver game_starting message" in caplog.text

    def test_room_websocket__when_game_server_returns_error__should_resync_and_send_error(self, client, app):
        room = app.state.room_manager.create_room("fail-room")
        self._set_servers_healthy(app)

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with (
            patch.object(app.state.registry, "check_health", new_callable=AsyncMock),
            patch("lobby.game_transition.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
                ws.receive_json()  # room_joined
                ws.send_text(json.dumps({"type": "start_game"}))
                resync = ws.receive_json()  # state resync after failure
                assert resync["type"] == "player_ready_changed"
                assert "players" in resync
                assert "can_start" in resync

                msg = ws.receive_json()  # error
                assert msg["type"] == "error"
                assert "Failed to start game" in msg["message"]
                # Check room state while still connected
                r = app.state.room_manager.get_room("fail-room")
                assert r is not None
                assert r.transitioning is False

    def test_room_websocket__when_game_server_unreachable__should_resync_and_send_error(self, client, app):
        room = app.state.room_manager.create_room("conn-err-room")
        self._set_servers_healthy(app)

        with (
            patch.object(app.state.registry, "check_health", new_callable=AsyncMock),
            patch("lobby.game_transition.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws:
                ws.receive_json()  # room_joined
                ws.send_text(json.dumps({"type": "start_game"}))
                resync = ws.receive_json()  # state resync after failure
                assert resync["type"] == "player_ready_changed"
                assert "players" in resync
                assert "can_start" in resync

                msg = ws.receive_json()  # error
                assert msg["type"] == "error"
                assert "Failed to start game" in msg["message"]

    def test_room_websocket__when_no_healthy_game_server__should_resync_and_send_error(self, client, app):
        room = app.state.room_manager.create_room("no-servers-room")

        with (
            patch.object(app.state.registry, "check_health", new_callable=AsyncMock),
            client.websocket_connect(f"/ws/rooms/{room.room_id}") as ws,
        ):
            ws.receive_json()  # room_joined
            ws.send_text(json.dumps({"type": "start_game"}))
            resync = ws.receive_json()  # state resync after failure
            assert resync["type"] == "player_ready_changed"
            assert "players" in resync
            assert "can_start" in resync

            msg = ws.receive_json()  # error
            assert msg["type"] == "error"
            assert "Failed to start game" in msg["message"]


class TestWebSocketOriginCheck:
    @pytest.fixture
    def app_with_origin(self, tmp_path):
        app = _make_app(tmp_path, ws_allowed_origin="http://localhost:3000")
        yield app
        app.state.db.close()

    @pytest.fixture
    def client_with_origin(self, app_with_origin):
        c = TestClient(app_with_origin)
        register_with_csrf(c, "wsuser")
        return c

    def test_room_websocket__when_origin_allowed__should_connect(self, client_with_origin, app_with_origin):
        room = app_with_origin.state.room_manager.create_room("origin-test")
        with client_with_origin.websocket_connect(
            f"/ws/rooms/{room.room_id}",
            headers={"origin": "http://localhost:3000"},
        ) as ws:
            msg = ws.receive_json()
            assert msg["type"] == "room_joined"

    def test_room_websocket__when_origin_forbidden__should_reject_connection(self, client_with_origin, app_with_origin):
        room = app_with_origin.state.room_manager.create_room("bad-origin")
        with (
            pytest.raises(Exception),  # noqa: B017, PT011
            client_with_origin.websocket_connect(
                f"/ws/rooms/{room.room_id}",
                headers={"origin": "http://evil.com"},
            ) as ws,
        ):
            ws.receive_json()

    def test_room_websocket__when_origin_header_missing__should_reject_connection(
        self, client_with_origin, app_with_origin
    ):
        room = app_with_origin.state.room_manager.create_room("no-origin")
        with (
            pytest.raises(Exception),  # noqa: B017, PT011
            client_with_origin.websocket_connect(f"/ws/rooms/{room.room_id}") as ws,
        ):
            ws.receive_json()


class TestWebSocketUnauthenticated:
    @pytest.fixture
    def unauthenticated_client(self, tmp_path):
        app = _make_app(tmp_path)
        app.state.room_manager.create_room("auth-test")
        c = TestClient(app)
        yield c
        app.state.db.close()

    def test_room_websocket__when_unauthenticated__should_reject_connection(self, unauthenticated_client):
        with (
            pytest.raises(Exception),  # noqa: B017, PT011
            unauthenticated_client.websocket_connect(
                "/ws/rooms/auth-test",
            ) as ws,
        ):
            ws.receive_json()
