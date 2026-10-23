import hashlib
import json
import secrets
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from lobby.auth.csrf import CSRF_COOKIE_NAME
from lobby.server.app import create_app
from lobby.settings import LobbyServerSettings
from shared.auth.settings import AuthSettings
from shared.dal.models import AccountType, Player

if TYPE_CHECKING:
    from collections.abc import Callable

TEST_SECRET = "test-ticket-secret"


def _make_client(tmp_path):
    config_file = tmp_path / "servers.yaml"
    servers_yaml = """
servers:
  - name: "test-server"
    url: "http://localhost:8711"
"""
    config_file.write_text(servers_yaml)

    static_dir = tmp_path / "public"
    (static_dir / "styles").mkdir(parents=True)
    (static_dir / "styles" / "lobby.css").write_text("body { color: red; }")

    game_assets_dir = tmp_path / "dist"
    game_assets_dir.mkdir()

    assets_dir = game_assets_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "game-test.js").write_text("console.log('test');")
    (assets_dir / "game-test.css").write_text("body{}")
    (assets_dir / "lobby-test.js").write_text("console.log('lobby');")
    (assets_dir / "lobby-test.css").write_text("body{}")

    vite_dir = game_assets_dir / ".vite"
    vite_dir.mkdir()
    (vite_dir / "manifest.json").write_text(
        json.dumps(
            {
                "src/index.ts": {"file": "assets/game-test.js", "css": ["assets/game-test.css"], "isEntry": True},
                "src/lobby/index.ts": {
                    "file": "assets/lobby-test.js",
                    "css": ["assets/lobby-test.css"],
                    "isEntry": True,
                },
            },
        ),
    )

    app = create_app(
        settings=LobbyServerSettings(
            config_path=config_file,
            static_dir=str(static_dir),
            game_assets_dir=str(game_assets_dir),
        ),
        auth_settings=AuthSettings(
            game_ticket_secret=TEST_SECRET,
            database_path=str(tmp_path / "test.db"),
            cookie_secure=False,
        ),
    )
    return TestClient(app)


def _get_csrf_token(client: TestClient, path: str = "/login") -> str:
    response = client.get(path)
    token = response.cookies.get(CSRF_COOKIE_NAME) or client.cookies.get(CSRF_COOKIE_NAME)
    assert token, f"CSRF cookie not available after GET {path}"
    return token


def _register_user(client: TestClient, username: str, password: str = "securepass123") -> None:  # noqa: S107
    csrf = _get_csrf_token(client, "/register")
    client.post(
        "/register",
        data={
            "username": username,
            "password": password,
            "confirm_password": password,
            "csrf_token": csrf,
        },
    )


def _insert_player(client, player: Player) -> None:
    with closing(sqlite3.connect(client.app.state.auth_settings.database_path)) as conn, conn:
        conn.execute(
            "INSERT INTO players (id, username, api_key_hash, data) VALUES (?, ?, ?, ?)",
            (player.user_id, player.username, player.api_key_hash, player.model_dump_json()),
        )


def _insert_bot(client, *, user_id: str, username: str) -> tuple[str, str]:
    raw_api_key = secrets.token_urlsafe(32)
    api_key_hash = hashlib.sha256(raw_api_key.encode()).hexdigest()

    player = Player(
        user_id=user_id,
        username=username,
        password_hash="!",
        account_type=AccountType.BOT,
        api_key_hash=api_key_hash,
    )
    _insert_player(client, player)
    return player.user_id, raw_api_key


class TestAuthEndpoints:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            yield c

    def test_register_route__when_get__should_render_form_with_confirm_password(self, client):
        response = client.get("/register")
        assert response.status_code == 200
        assert "Register" in response.text
        assert "confirm_password" in response.text

    def test_register_route__when_valid_post__should_redirect_to_lobby_with_session(self, client):
        csrf = _get_csrf_token(client, "/register")

        response = client.post(
            "/register",
            data={
                "username": "newuser",
                "password": "securepass123",
                "confirm_password": "securepass123",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "session_id" in response.cookies

    def test_register_route__when_passwords_differ__should_show_error(self, client):
        csrf = _get_csrf_token(client, "/register")

        response = client.post(
            "/register",
            data={
                "username": "newuser",
                "password": "securepass123",
                "confirm_password": "different",
                "csrf_token": csrf,
            },
        )
        assert response.status_code == 200
        assert "Passwords do not match" in response.text

    def test_register_route__when_username_taken__should_show_error(self, client):
        _register_user(client, username="takenuser")
        csrf = _get_csrf_token(client, "/register")

        response = client.post(
            "/register",
            data={
                "username": "takenuser",
                "password": "securepass456",
                "confirm_password": "securepass456",
                "csrf_token": csrf,
            },
        )
        assert response.status_code == 200
        assert "already taken" in response.text

    def test_register_route__when_password_too_short__should_show_error(self, client):
        csrf = _get_csrf_token(client, "/register")

        response = client.post(
            "/register",
            data={
                "username": "newuser",
                "password": "short",
                "confirm_password": "short",
                "csrf_token": csrf,
            },
        )
        assert response.status_code == 200
        assert "Password must be" in response.text

    def test_login_route__when_credentials_valid__should_redirect_to_lobby_with_session(self, client):
        _register_user(client, username="loginuser")
        csrf = _get_csrf_token(client, "/login")

        response = client.post(
            "/login",
            data={"username": "loginuser", "password": "securepass123", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"
        assert "session_id" in response.cookies

    def test_login_route__when_password_wrong__should_show_error(self, client):
        _register_user(client, username="loginuser")
        csrf = _get_csrf_token(client, "/login")

        response = client.post(
            "/login",
            data={"username": "loginuser", "password": "wrongpassword", "csrf_token": csrf},
        )
        assert response.status_code == 200
        assert "Invalid credentials" in response.text

    def test_login_route__when_user_unknown__should_show_error(self, client):
        csrf = _get_csrf_token(client, "/login")

        response = client.post(
            "/login",
            data={"username": "ghost", "password": "securepass123", "csrf_token": csrf},
        )
        assert response.status_code == 200
        assert "Invalid credentials" in response.text

    def test_logout_route__when_posted__should_clear_session_and_redirect_to_login(self, client):
        _register_user(client, username="logoutuser")
        # After register, the CSRF cookie is already set. Read it for the logout POST.
        csrf = client.cookies.get(CSRF_COOKIE_NAME)

        response = client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

        # After logout, protected routes redirect to login with next param
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        location = urlparse(response.headers["location"])
        assert location.path == "/login"
        assert "next" in parse_qs(location.query)

    def test_lobby_page__when_authenticated__should_show_username_and_logout(self, client):
        _register_user(client, username="lobbyuser")

        response = client.get("/")
        assert response.status_code == 200
        assert "lobbyuser" in response.text
        assert "Logout" in response.text


class TestCreateRoomRedirect:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            _register_user(c, username="gameuser")
            yield c

    def test_create_room_route__when_posted__should_redirect_to_room_page(self, client):
        csrf = client.cookies.get(CSRF_COOKIE_NAME)

        response = client.post("/rooms/new", data={"csrf_token": csrf}, follow_redirects=False)
        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith("/rooms/")
        assert "game_ticket=" not in location

    def test_create_room_route__when_posted__should_create_room_with_four_ai_seats(self, client):
        csrf = client.cookies.get(CSRF_COOKIE_NAME)

        response = client.post("/rooms/new", data={"csrf_token": csrf}, follow_redirects=False)
        location = response.headers["location"]
        room_id = location.split("/rooms/")[1]
        room = client.app.state.room_manager.get_room(room_id)
        assert room is not None
        # Empty room: no humans joined yet, all 4 seats are bots
        assert room.num_ai_players == 4


class TestJoinRoomRedirect:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            _register_user(c, username="joinuser")
            yield c

    def test_join_room_route__when_room_exists__should_redirect_to_room_page(self, client):
        room_manager = client.app.state.room_manager
        room_manager.create_room("test-room-123")

        csrf = client.cookies.get(CSRF_COOKIE_NAME)

        response = client.post(
            "/rooms/test-room-123/join",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/rooms/test-room-123"

    def test_join_room_route__when_room_missing__should_show_error(self, client):
        csrf = client.cookies.get(CSRF_COOKIE_NAME)

        response = client.post("/rooms/no-such-room/join", data={"csrf_token": csrf})
        assert response.status_code == 200
        assert "Room not found" in response.text


class TestBotAuth:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            yield c

    def test_bot_auth_route__when_key_and_room_valid__should_return_room_info_and_bot_session(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-test-id", username="TestBot")
        room_manager = client.app.state.room_manager
        room_manager.create_room("room-bot")

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

    def test_bot_auth_route__when_room_id_missing__should_return_400(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-test-id", username="TestBot")

        response = client.post(
            "/api/auth/bot",
            json={},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "required" in response.json()["error"]

    def test_bot_auth_route__when_room_not_found__should_return_404(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-test-id", username="TestBot")

        response = client.post(
            "/api/auth/bot",
            json={"room_id": "no-such-room"},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 404
        assert response.json()["error"] == "Room not found"

    def test_bot_auth_route__when_body_not_json__should_return_400(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-test-id", username="TestBot")

        response = client.post(
            "/api/auth/bot",
            content="not json",
            headers={"content-type": "application/json", "x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["error"]

    def test_bot_auth_route__when_body_is_json_array__should_return_400(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-test-id", username="TestBot")

        response = client.post(
            "/api/auth/bot",
            json=[{"room_id": "room-1"}],
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["error"]


class TestBotCreateRoom:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            yield c

    def test_bot_create_room_route__when_key_valid__should_create_room_with_four_ai_seats(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-room-id", username="RoomBot")

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
        room = client.app.state.room_manager.get_room(data["room_id"])
        assert room is not None
        # Empty room: no humans joined yet, all 4 seats are bots
        assert room.num_ai_players == 4

    def test_bot_create_room_route__when_num_ai_players_given__should_return_400(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-room-id", username="RoomBot")

        response = client.post(
            "/api/rooms",
            json={"num_ai_players": 2},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "num_ai_players" in response.json()["error"]

    def test_bot_create_room_route__when_min_human_players_given__should_apply_it(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-room-id", username="RoomBot")

        response = client.post(
            "/api/rooms",
            json={"min_human_players": 4},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 201
        data = response.json()
        room = client.app.state.room_manager.get_room(data["room_id"])
        assert room is not None
        assert room.min_human_players == 4

    def test_bot_create_room_route__when_min_human_players_out_of_range__should_return_400(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-room-id", username="RoomBot")

        response = client.post(
            "/api/rooms",
            json={"min_human_players": 5},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "min_human_players" in response.json()["error"]

    def test_bot_create_room_route__when_min_human_players_not_int__should_return_400(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-room-id", username="RoomBot")

        response = client.post(
            "/api/rooms",
            json={"min_human_players": "four"},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "min_human_players" in response.json()["error"]

    def test_bot_create_room_route__when_min_human_players_boolean__should_return_400(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-room-id", username="RoomBot")

        response = client.post(
            "/api/rooms",
            json={"min_human_players": True},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "min_human_players" in response.json()["error"]

    def test_bot_create_room_route__when_body_not_json__should_return_400(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-room-id", username="RoomBot")

        response = client.post(
            "/api/rooms",
            content="not json",
            headers={"content-type": "application/json", "x-api-key": raw_key},
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["error"]


class TestBotOnlyRoutes:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            yield c

    def test_bot_auth_route__when_api_key_valid__should_issue_session_with_bot_account_type(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-test-id", username="TestBot")
        room_manager = client.app.state.room_manager
        room_manager.create_room("room-bot")

        response = client.post(
            "/api/auth/bot",
            json={"room_id": "room-bot"},
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 200
        data = response.json()

        # Use the bot session to verify it preserves bot identity
        auth_service = client.app.state.auth_service
        session = auth_service.validate_session(data["session_id"])
        assert session is not None
        assert session.account_type == AccountType.BOT


class TestApiKeyProtectedEndpoints:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            yield c

    def test_servers_route__when_api_key_valid__should_list_servers(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-srv-id", username="ServerBot")

        response = client.get(
            "/servers",
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 200
        assert "servers" in response.json()


def _no_credential(_client: TestClient) -> dict[str, str]:
    return {}


def _unknown_api_key(_client: TestClient) -> dict[str, str]:
    return {"x-api-key": "bogus-key"}


def _human_session(client: TestClient) -> dict[str, str]:
    _register_user(client, username="humanuser")
    return {}


AUTH_REQUIRED_BODY = b'{"error":"Authentication required"}'
AUTH_REQUIRED_HEADERS = {"content-type": "application/json", "content-length": "35"}
BOT_REQUIRED_BODY = b'{"error":"Bot account required"}'
BOT_REQUIRED_HEADERS = {"content-type": "application/json", "content-length": "32"}
BOT_ONLY_ROUTES = ["/api/rooms", "/api/auth/bot", "/api/matchmaking/join"]


@dataclass(frozen=True)
class _RejectedRequest:
    credential: Callable[[TestClient], dict[str, str]]
    method: str
    path: str
    status: int
    body: bytes
    headers: dict[str, str]


class TestAuthPolicyWiring:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            yield c

    @pytest.mark.parametrize(
        "case",
        [
            *[
                pytest.param(
                    _RejectedRequest(_no_credential, "POST", path, 401, AUTH_REQUIRED_BODY, AUTH_REQUIRED_HEADERS),
                    id=f"no_credential-{path}",
                )
                for path in BOT_ONLY_ROUTES
            ],
            pytest.param(
                _RejectedRequest(_no_credential, "GET", "/servers", 401, AUTH_REQUIRED_BODY, AUTH_REQUIRED_HEADERS),
                id="no_credential-/servers",
            ),
            pytest.param(
                _RejectedRequest(
                    _unknown_api_key, "POST", "/api/rooms", 401, AUTH_REQUIRED_BODY, AUTH_REQUIRED_HEADERS
                ),
                id="unknown_api_key-/api/rooms",
            ),
            *[
                pytest.param(
                    _RejectedRequest(_human_session, "POST", path, 403, BOT_REQUIRED_BODY, BOT_REQUIRED_HEADERS),
                    id=f"human_session-{path}",
                )
                for path in BOT_ONLY_ROUTES
            ],
            pytest.param(
                _RejectedRequest(
                    _no_credential, "GET", "/", 303, b"", {"location": "/login?next=%2F", "content-length": "0"}
                ),
                id="no_credential-/",
            ),
        ],
    )
    def test_auth_policy__when_credential_not_accepted__should_reject_with_policy_status_and_body(self, client, case):
        headers = case.credential(client)

        response = client.request(case.method, case.path, headers=headers, follow_redirects=False)
        assert response.status_code == case.status
        assert response.content == case.body
        assert {name: response.headers.get(name) for name in case.headers} == case.headers


class TestCsrfProtection:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            yield c

    def test_csrf_protection__when_login_post_has_no_token__should_return_403(self, client):
        response = client.post("/login", data={"username": "a", "password": "b"})
        assert response.status_code == 403

    def test_csrf_protection__when_register_post_has_no_token__should_return_403(self, client):
        response = client.post(
            "/register",
            data={"username": "a", "password": "b", "confirm_password": "b"},
        )
        assert response.status_code == 403

    def test_csrf_protection__when_logout_post_has_no_cookie__should_return_403(self, client):
        _register_user(client, username="csrfuser")
        # Clear the CSRF cookie to simulate a cross-site request
        client.cookies.delete(CSRF_COOKIE_NAME)

        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 403

    def test_csrf_protection__when_create_room_post_has_no_cookie__should_return_403(self, client):
        _register_user(client, username="csrfuser")
        client.cookies.delete(CSRF_COOKIE_NAME)

        response = client.post("/rooms/new", follow_redirects=False)
        assert response.status_code == 403

    def test_csrf_protection__when_join_room_post_has_no_cookie__should_return_403(self, client):
        _register_user(client, username="csrfuser")
        client.cookies.delete(CSRF_COOKIE_NAME)

        response = client.post("/rooms/some-room/join", follow_redirects=False)
        assert response.status_code == 403

    def test_csrf_protection__when_login_post_uses_token_from_get__should_succeed(self, client):
        _register_user(client, username="logincsrf")
        csrf = _get_csrf_token(client, "/login")

        response = client.post(
            "/login",
            data={"username": "logincsrf", "password": "securepass123", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert response.status_code == 303

    def test_csrf_protection__when_login_page_first_visited__should_set_cookie(self, client):
        response = client.get("/login")
        assert CSRF_COOKIE_NAME in response.cookies

    def test_csrf_protection__when_login_page_rendered__should_include_token_field(self, client):
        response = client.get("/login")
        assert 'name="csrf_token"' in response.text

    def test_csrf_protection__when_token_mismatches_cookie__should_return_403(self, client):
        _get_csrf_token(client, "/login")
        response = client.post(
            "/login",
            data={"username": "a", "password": "b", "csrf_token": "forged-token"},
        )
        assert response.status_code == 403


class TestBotMatchmakingAuth:
    @pytest.fixture
    def client(self, tmp_path):
        with _make_client(tmp_path) as c:
            yield c

    def test_bot_matchmaking_join_route__when_key_valid__should_return_bot_session_and_ws_url(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-mm-id", username="MatchBot")

        response = client.post(
            "/api/matchmaking/join",
            headers={"x-api-key": raw_key},
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "/ws/matchmaking" in data["ws_url"]

        # Verify the session is valid and preserves bot identity
        auth_service = client.app.state.auth_service
        session = auth_service.validate_session(data["session_id"])
        assert session is not None
        assert session.username == "MatchBot"
        assert session.account_type == AccountType.BOT

    def test_bot_matchmaking_join_route__when_session_validated__should_match_bot_user(self, client):
        _, raw_key = _insert_bot(client, user_id="bot-ws-id", username="WSBot")
        response = client.post(
            "/api/matchmaking/join",
            headers={"x-api-key": raw_key},
        )
        data = response.json()

        # Verify the session_id from the endpoint can be validated by the auth service
        # (the same validation the WebSocket auth backend uses for session_id query param)
        auth_service = client.app.state.auth_service
        session = auth_service.validate_session(data["session_id"])
        assert session is not None
        assert session.user_id == "bot-ws-id"
        assert session.account_type == AccountType.BOT
