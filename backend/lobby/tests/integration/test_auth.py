"""Integration tests for lobby auth endpoints and full login-to-game-ticket flow."""

import hashlib
import secrets
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.server.settings import LobbyServerSettings
from shared.auth.game_ticket import verify_game_ticket
from shared.auth.models import AccountType, Player
from shared.auth.settings import AuthSettings

TEST_SECRET = "test-ticket-secret"


def _make_client(tmp_path):
    """Create a lobby TestClient backed by a temporary SQLite database."""
    config_file = tmp_path / "servers.yaml"
    config_file.write_text(
        """
servers:
  - name: "test-server"
    url: "http://localhost:8711"
""",
    )
    static_dir = tmp_path / "public"
    (static_dir / "styles").mkdir(parents=True)
    (static_dir / "styles" / "lobby.css").write_text("body { color: red; }")

    game_assets_dir = tmp_path / "dist"
    game_assets_dir.mkdir()
    (game_assets_dir / "manifest.json").write_text('{"js": "index-test.js", "css": "index-test.css"}')
    (game_assets_dir / "index-test.js").write_text("console.log('test');")
    (game_assets_dir / "index-test.css").write_text("body{}")

    app = create_app(
        settings=LobbyServerSettings(
            config_path=config_file,
            static_dir=str(static_dir),
            game_assets_dir=str(game_assets_dir),
        ),
        auth_settings=AuthSettings(
            game_ticket_secret=TEST_SECRET,
            database_path=str(tmp_path / "test.db"),
        ),
    )
    return TestClient(app)


def _insert_bot(client, user_id: str, username: str) -> tuple[str, str]:
    """Insert a bot player directly into the SQLite database. Returns (user_id, raw_api_key)."""
    db = client.app.state.db
    raw_api_key = secrets.token_urlsafe(32)
    api_key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()
    player = Player(
        user_id=user_id,
        username=username,
        password_hash="!",
        account_type=AccountType.BOT,
        api_key_hash=api_key_hash,
    )
    db.connection.execute(
        "INSERT INTO players (id, username, api_key_hash, data) VALUES (?, ?, ?, ?)",
        (player.user_id, player.username, player.api_key_hash, player.model_dump_json()),
    )
    db.connection.commit()
    return player.user_id, raw_api_key


def _insert_human_with_key(client, user_id: str, username: str, raw_key: str) -> None:
    """Insert a human player with an api_key_hash directly into the SQLite database."""
    db = client.app.state.db
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    player = Player(
        user_id=user_id,
        username=username,
        password_hash="$2b$12$fakehashvalue",
        account_type=AccountType.HUMAN,
        api_key_hash=key_hash,
    )
    db.connection.execute(
        "INSERT INTO players (id, username, api_key_hash, data) VALUES (?, ?, ?, ?)",
        (player.user_id, player.username, player.api_key_hash, player.model_dump_json()),
    )
    db.connection.commit()


class TestAuthEndpoints:
    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        yield c
        c.app.state.db.close()

    def test_login_page_renders(self, client):
        response = client.get("/login")
        assert response.status_code == 200
        assert "Login" in response.text
        assert "username" in response.text
        assert "password" in response.text

    def test_register_page_renders(self, client):
        response = client.get("/register")
        assert response.status_code == 200
        assert "Register" in response.text
        assert "confirm_password" in response.text

    def test_register_and_auto_login(self, client):
        response = client.post(
            "/register",
            data={"username": "newuser", "password": "securepass123", "confirm_password": "securepass123"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "session_id" in response.cookies

    def test_register_password_mismatch(self, client):
        response = client.post(
            "/register",
            data={"username": "newuser", "password": "securepass123", "confirm_password": "different"},
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    def test_register_duplicate_username(self, client):
        client.post(
            "/register",
            data={"username": "takenuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        response = client.post(
            "/register",
            data={"username": "takenuser", "password": "securepass456", "confirm_password": "securepass456"},
        )
        assert response.status_code == 200
        assert "already taken" in response.text

    def test_register_short_password(self, client):
        response = client.post(
            "/register",
            data={"username": "newuser", "password": "short", "confirm_password": "short"},
        )
        assert response.status_code == 200
        assert "Password must be" in response.text

    def test_login_success(self, client):
        client.post(
            "/register",
            data={"username": "loginuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        response = client.post(
            "/login",
            data={"username": "loginuser", "password": "securepass123"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "session_id" in response.cookies

    def test_login_wrong_password(self, client):
        client.post(
            "/register",
            data={"username": "loginuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        response = client.post(
            "/login",
            data={"username": "loginuser", "password": "wrongpassword"},
        )
        assert response.status_code == 200
        assert "Invalid credentials" in response.text

    def test_login_unknown_user(self, client):
        response = client.post(
            "/login",
            data={"username": "ghost", "password": "securepass123"},
        )
        assert response.status_code == 200
        assert "Invalid credentials" in response.text

    def test_logout_clears_session(self, client):
        client.post(
            "/register",
            data={"username": "logoutuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

        # After logout, protected routes redirect to login with next param
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        location = urlparse(response.headers["location"])
        assert location.path == "/login"
        assert "next" in parse_qs(location.query)

    def test_unauthenticated_lobby_redirects_to_login(self, client):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        location = urlparse(response.headers["location"])
        assert location.path == "/login"
        assert "next" in parse_qs(location.query)

    def test_authenticated_lobby_shows_username(self, client):
        patcher = self._mock_httpx_no_healthy_servers()
        try:
            client.post(
                "/register",
                data={"username": "lobbyuser", "password": "securepass123", "confirm_password": "securepass123"},
            )
            response = client.get("/")
            assert response.status_code == 200
            assert "lobbyuser" in response.text
            assert "Logout" in response.text
        finally:
            patcher.stop()

    def _mock_httpx_no_healthy_servers(self):
        """Patch httpx so health checks fail (no healthy servers, empty room list)."""
        patcher = patch("httpx.AsyncClient")
        mock_client = patcher.start()
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_instance.get.side_effect = httpx.RequestError("Connection refused")
        return patcher


class TestCreateRoomWithTicket:
    """Test that room creation signs a game ticket and redirects properly."""

    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        c.post(
            "/register",
            data={"username": "gameuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        yield c
        c.app.state.db.close()

    def _mock_httpx_for_create(self):
        """Patch httpx so health checks pass and room creation succeeds."""
        mock_health_response = AsyncMock()
        mock_health_response.status_code = 200
        mock_create_response = AsyncMock()
        mock_create_response.status_code = 201
        mock_rooms_response = MagicMock()
        mock_rooms_response.status_code = 200
        mock_rooms_response.json.return_value = {"rooms": []}

        patcher = patch("httpx.AsyncClient")
        mock_client = patcher.start()
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance

        def get_side_effect(url):
            if "/rooms" in url:
                return mock_rooms_response
            return mock_health_response

        mock_instance.get.side_effect = get_side_effect
        mock_instance.post.return_value = mock_create_response
        return patcher

    def test_create_room_redirects_with_game_ticket(self, client):
        patcher = self._mock_httpx_for_create()
        try:
            response = client.post("/rooms/new", follow_redirects=False)
            assert response.status_code == 303
            location = response.headers["location"]
            assert location.startswith("/game?")
            assert "game_ticket=" in location
            assert "ws_url=" in location
            # No player_name in URL params anymore
            assert "player_name=" not in location
        finally:
            patcher.stop()

    def test_create_room_ticket_is_valid(self, client):
        patcher = self._mock_httpx_for_create()
        try:
            response = client.post("/rooms/new", follow_redirects=False)
            location = response.headers["location"]
            parsed = urlparse(location)
            params = parse_qs(parsed.query)
            game_ticket = params["game_ticket"][0]

            ticket = verify_game_ticket(game_ticket, TEST_SECRET)
            assert ticket is not None
            assert ticket.username == "gameuser"
        finally:
            patcher.stop()


class TestJoinRoomWithTicket:
    """Test that joining an existing room signs a game ticket."""

    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        c.post(
            "/register",
            data={"username": "joinuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        yield c
        c.app.state.db.close()

    def _mock_httpx_with_rooms(self, rooms):
        mock_health_response = MagicMock()
        mock_health_response.status_code = 200
        mock_rooms_response = MagicMock()
        mock_rooms_response.status_code = 200
        mock_rooms_response.json.return_value = {"rooms": rooms}

        patcher = patch("httpx.AsyncClient")
        mock_client = patcher.start()
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance

        def get_side_effect(url):
            if "/health" in url:
                return mock_health_response
            if "/rooms" in url:
                return mock_rooms_response
            return mock_health_response

        mock_instance.get.side_effect = get_side_effect
        return patcher

    def test_join_room_redirects_with_game_ticket(self, client):
        rooms = [
            {
                "room_id": "room-abc",
                "player_count": 1,
                "players_needed": 2,
                "server_url": "http://localhost:8711",
            },
        ]
        patcher = self._mock_httpx_with_rooms(rooms)
        try:
            response = client.post("/rooms/room-abc/join", follow_redirects=False)
            assert response.status_code == 303
            location = response.headers["location"]
            assert "game_ticket=" in location
            assert "ws_url=" in location

            parsed = urlparse(location)
            params = parse_qs(parsed.query)
            game_ticket = params["game_ticket"][0]

            ticket = verify_game_ticket(game_ticket, TEST_SECRET)
            assert ticket is not None
            assert ticket.username == "joinuser"
            assert ticket.room_id == "room-abc"
        finally:
            patcher.stop()

    def test_join_nonexistent_room_shows_error(self, client):
        patcher = self._mock_httpx_with_rooms([])
        try:
            response = client.post("/rooms/no-such-room/join")
            assert response.status_code == 200
            assert "Room not found" in response.text
        finally:
            patcher.stop()


class TestBotAuth:
    """Test bot API key authentication endpoint."""

    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        yield c
        c.app.state.db.close()

    def _mock_httpx_with_rooms(self, rooms):
        mock_health_response = MagicMock()
        mock_health_response.status_code = 200
        mock_rooms_response = MagicMock()
        mock_rooms_response.status_code = 200
        mock_rooms_response.json.return_value = {"rooms": rooms}

        patcher = patch("httpx.AsyncClient")
        mock_client = patcher.start()
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance

        def get_side_effect(url):
            if "/health" in url:
                return mock_health_response
            if "/rooms" in url:
                return mock_rooms_response
            return mock_health_response

        mock_instance.get.side_effect = get_side_effect
        return patcher

    def test_bot_auth_exchanges_key_for_ticket(self, client):
        user_id, raw_key = _insert_bot(client, "bot-test-id", "TestBot")
        rooms = [
            {
                "room_id": "room-bot",
                "player_count": 1,
                "players_needed": 2,
                "server_url": "http://localhost:8711",
            },
        ]
        patcher = self._mock_httpx_with_rooms(rooms)
        try:
            response = client.post(
                "/api/auth/bot",
                json={"api_key": raw_key, "room_id": "room-bot"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "game_ticket" in data
            assert "ws_url" in data

            ticket = verify_game_ticket(data["game_ticket"], TEST_SECRET)
            assert ticket is not None
            assert ticket.username == "TestBot"
            assert ticket.room_id == "room-bot"
            assert ticket.user_id == user_id
        finally:
            patcher.stop()

    def test_bot_auth_invalid_key_returns_401(self, client):
        response = client.post(
            "/api/auth/bot",
            json={"api_key": "bogus-key", "room_id": "room-1"},
        )
        assert response.status_code == 401
        assert response.json()["error"] == "Invalid API key"

    def test_bot_auth_missing_fields_returns_400(self, client):
        response = client.post(
            "/api/auth/bot",
            json={"api_key": "some-key"},
        )
        assert response.status_code == 400
        assert "required" in response.json()["error"]

    def test_bot_auth_invalid_json_returns_400(self, client):
        response = client.post(
            "/api/auth/bot",
            content="not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["error"]

    def test_bot_auth_json_array_body_returns_400(self, client):
        response = client.post(
            "/api/auth/bot",
            json=[{"api_key": "key", "room_id": "room-1"}],
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["error"]

    def test_bot_auth_non_string_api_key_returns_400(self, client):
        response = client.post(
            "/api/auth/bot",
            json={"api_key": 123, "room_id": "room-1"},
        )
        assert response.status_code == 400
        assert "non-empty strings" in response.json()["error"]

    def test_bot_auth_non_string_room_id_returns_400(self, client):
        response = client.post(
            "/api/auth/bot",
            json={"api_key": "some-key", "room_id": ["room-1"]},
        )
        assert response.status_code == 400
        assert "non-empty strings" in response.json()["error"]

    def test_bot_auth_room_not_found_returns_404(self, client):
        _, raw_key = _insert_bot(client, "bot-test-id", "TestBot")
        patcher = self._mock_httpx_with_rooms([])
        try:
            response = client.post(
                "/api/auth/bot",
                json={"api_key": raw_key, "room_id": "no-such-room"},
            )
            assert response.status_code == 404
            assert response.json()["error"] == "Room not found"
        finally:
            patcher.stop()

    def test_bot_auth_rejects_human_api_key_hash(self, client):
        """Defense-in-depth: even if a human account somehow gets an api_key_hash, reject it."""
        raw_key = "sneaky-human-key"
        _insert_human_with_key(client, "human-with-key", "SneakyHuman", raw_key)

        response = client.post(
            "/api/auth/bot",
            json={"api_key": raw_key, "room_id": "room-1"},
        )
        assert response.status_code == 401
        assert response.json()["error"] == "Invalid API key"


class TestApiKeyProtectedEndpoints:
    """Test that bot API keys in the X-API-Key header grant access to protected endpoints."""

    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        yield c
        c.app.state.db.close()

    def _mock_httpx_for_create(self):
        """Patch httpx so health checks pass and room creation succeeds."""
        mock_health_response = AsyncMock()
        mock_health_response.status_code = 200
        mock_create_response = AsyncMock()
        mock_create_response.status_code = 201

        patcher = patch("httpx.AsyncClient")
        mock_client = patcher.start()
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_instance.get.return_value = mock_health_response
        mock_instance.post.return_value = mock_create_response
        return patcher

    def _mock_httpx_with_rooms(self, rooms):
        mock_health_response = MagicMock()
        mock_health_response.status_code = 200
        mock_rooms_response = MagicMock()
        mock_rooms_response.status_code = 200
        mock_rooms_response.json.return_value = {"rooms": rooms}

        patcher = patch("httpx.AsyncClient")
        mock_client = patcher.start()
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance

        def get_side_effect(url):
            if "/health" in url:
                return mock_health_response
            if "/rooms" in url:
                return mock_rooms_response
            return mock_health_response

        mock_instance.get.side_effect = get_side_effect
        return patcher

    def test_bot_can_create_room_via_api_key_header(self, client):
        _, raw_key = _insert_bot(client, "bot-create-id", "CreateBot")
        patcher = self._mock_httpx_for_create()
        try:
            response = client.post(
                "/rooms",
                headers={"x-api-key": raw_key},
            )
            assert response.status_code == 201
            data = response.json()
            assert "room_id" in data
            assert "websocket_url" in data
            assert "server_name" in data
        finally:
            patcher.stop()

    def test_bot_can_list_rooms_via_api_key_header(self, client):
        _, raw_key = _insert_bot(client, "bot-list-id", "ListBot")
        rooms = [{"room_id": "room-1", "player_count": 1, "server_url": "http://localhost:8711"}]
        patcher = self._mock_httpx_with_rooms(rooms)
        try:
            response = client.get(
                "/rooms",
                headers={"x-api-key": raw_key},
            )
            assert response.status_code == 200
            assert len(response.json()["rooms"]) == 1
        finally:
            patcher.stop()

    def test_bot_can_list_servers_via_api_key_header(self, client):
        _, raw_key = _insert_bot(client, "bot-srv-id", "ServerBot")
        response = client.get(
            "/servers",
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 200
        assert "servers" in response.json()

    def test_invalid_api_key_returns_401(self, client):
        response = client.get(
            "/rooms",
            headers={"x-api-key": "bogus-key"},
        )
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}

    def test_human_account_api_key_returns_401(self, client):
        """Defense-in-depth: human accounts with an api_key_hash are rejected at middleware level."""
        raw_key = "sneaky-human-key"
        _insert_human_with_key(client, "human-api-id", "SneakyHuman", raw_key)

        response = client.get(
            "/rooms",
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}
