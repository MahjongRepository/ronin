"""Integration tests for lobby auth endpoints and full login flow."""

import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.server.settings import LobbyServerSettings
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
        client.post(
            "/register",
            data={"username": "lobbyuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        response = client.get("/")
        assert response.status_code == 200
        assert "lobbyuser" in response.text
        assert "Logout" in response.text


class TestCreateRoomRedirect:
    """Test that room creation redirects to the room page."""

    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        c.post(
            "/register",
            data={"username": "gameuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        yield c
        c.app.state.db.close()

    def test_create_room_redirects_to_room_page(self, client):
        response = client.post("/rooms/new", follow_redirects=False)
        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith("/rooms/")
        # No game ticket in URL
        assert "game_ticket=" not in location

    def test_create_room_creates_local_room(self, client):
        response = client.post("/rooms/new", follow_redirects=False)
        location = response.headers["location"]
        room_id = location.split("/rooms/")[1]
        room = client.app.state.room_manager.get_room(room_id)
        assert room is not None
        assert room.num_ai_players == 3


class TestJoinRoomRedirect:
    """Test that joining an existing room redirects to the room page."""

    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        c.post(
            "/register",
            data={"username": "joinuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        yield c
        c.app.state.db.close()

    def test_join_room_redirects_to_room_page(self, client):
        room_manager = client.app.state.room_manager
        room_manager.create_room("test-room-123", num_ai_players=3)

        response = client.post("/rooms/test-room-123/join", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/rooms/test-room-123"

    def test_join_nonexistent_room_shows_error(self, client):
        response = client.post("/rooms/no-such-room/join")
        assert response.status_code == 200
        assert "Room not found" in response.text


class TestBotAuth:
    """Test bot API key authentication via X-API-Key header."""

    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        yield c
        c.app.state.db.close()

    def test_bot_auth_returns_room_info(self, client):
        _, raw_key = _insert_bot(client, "bot-test-id", "TestBot")
        room_manager = client.app.state.room_manager
        room_manager.create_room("room-bot", num_ai_players=3)

        response = client.post(
            "/api/auth/bot",
            json={"room_id": "room-bot"},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["room_id"] == "room-bot"
        assert "/ws/rooms/room-bot" in data["ws_url"]
        assert "session_id" in data
        auth_service = client.app.state.auth_service
        session = auth_service.validate_session(data["session_id"])
        assert session is not None
        assert session.username == "TestBot"

    def test_bot_auth_invalid_key_returns_401(self, client):
        response = client.post(
            "/api/auth/bot",
            json={"room_id": "room-1"},
            headers={"x-api-key": "bogus-key"},
        )
        assert response.status_code == 401

    def test_bot_auth_missing_fields_returns_400(self, client):
        _, raw_key = _insert_bot(client, "bot-test-id", "TestBot")
        response = client.post(
            "/api/auth/bot",
            json={},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "required" in response.json()["error"]

    def test_bot_auth_room_not_found_returns_404(self, client):
        _, raw_key = _insert_bot(client, "bot-test-id", "TestBot")
        response = client.post(
            "/api/auth/bot",
            json={"room_id": "no-such-room"},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 404
        assert response.json()["error"] == "Room not found"

    def test_bot_auth_invalid_json_returns_400(self, client):
        _, raw_key = _insert_bot(client, "bot-test-id", "TestBot")
        response = client.post(
            "/api/auth/bot",
            content="not json",
            headers={"content-type": "application/json", "x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["error"]

    def test_bot_auth_json_array_body_returns_400(self, client):
        _, raw_key = _insert_bot(client, "bot-test-id", "TestBot")
        response = client.post(
            "/api/auth/bot",
            json=[{"room_id": "room-1"}],
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["error"]

    def test_bot_auth_rejects_human_api_key_hash(self, client):
        """Defense-in-depth: human accounts with an api_key_hash are rejected at middleware level."""
        raw_key = "sneaky-human-key"
        _insert_human_with_key(client, "human-with-key", "SneakyHuman", raw_key)

        response = client.post(
            "/api/auth/bot",
            json={"room_id": "room-1"},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 401


class TestBotCreateRoom:
    """Test bot room creation via POST /api/rooms with X-API-Key header."""

    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        yield c
        c.app.state.db.close()

    def test_create_room_returns_room_info(self, client):
        _, raw_key = _insert_bot(client, "bot-room-id", "RoomBot")
        response = client.post(
            "/api/rooms",
            json={},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 201
        data = response.json()
        assert "room_id" in data
        assert "session_id" in data
        assert "/ws/rooms/" in data["ws_url"]
        # Room actually exists in manager
        room = client.app.state.room_manager.get_room(data["room_id"])
        assert room is not None

    def test_create_room_custom_ai_players(self, client):
        _, raw_key = _insert_bot(client, "bot-room-id", "RoomBot")
        response = client.post(
            "/api/rooms",
            json={"num_ai_players": 2},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 201
        data = response.json()
        room = client.app.state.room_manager.get_room(data["room_id"])
        assert room is not None
        assert room.num_ai_players == 2

    def test_create_room_default_ai_players(self, client):
        _, raw_key = _insert_bot(client, "bot-room-id", "RoomBot")
        response = client.post(
            "/api/rooms",
            json={},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 201
        data = response.json()
        room = client.app.state.room_manager.get_room(data["room_id"])
        assert room.num_ai_players == 3

    def test_create_room_invalid_ai_count(self, client):
        _, raw_key = _insert_bot(client, "bot-room-id", "RoomBot")
        response = client.post(
            "/api/rooms",
            json={"num_ai_players": 5},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "num_ai_players" in response.json()["error"]

    def test_create_room_invalid_key_returns_401(self, client):
        response = client.post(
            "/api/rooms",
            json={},
            headers={"x-api-key": "bogus-key"},
        )
        assert response.status_code == 401

    def test_create_room_invalid_json_returns_400(self, client):
        _, raw_key = _insert_bot(client, "bot-room-id", "RoomBot")
        response = client.post(
            "/api/rooms",
            content="not json",
            headers={"content-type": "application/json", "x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["error"]

    def test_create_room_human_key_rejected(self, client):
        """Defense-in-depth: human accounts with an api_key_hash are rejected at middleware level."""
        raw_key = "sneaky-human-key"
        _insert_human_with_key(client, "human-room-id", "SneakyHuman", raw_key)
        response = client.post(
            "/api/rooms",
            json={},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 401


class TestApiKeyProtectedEndpoints:
    """Test that bot API keys in the X-API-Key header grant access to protected endpoints."""

    @pytest.fixture
    def client(self, tmp_path):
        c = _make_client(tmp_path)
        yield c
        c.app.state.db.close()

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
            "/servers",
            headers={"x-api-key": "bogus-key"},
        )
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}

    def test_human_account_api_key_returns_401(self, client):
        """Defense-in-depth: human accounts with an api_key_hash are rejected at middleware level."""
        raw_key = "sneaky-human-key"
        _insert_human_with_key(client, "human-api-id", "SneakyHuman", raw_key)

        response = client.get(
            "/servers",
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 401
        assert response.json() == {"error": "Authentication required"}
