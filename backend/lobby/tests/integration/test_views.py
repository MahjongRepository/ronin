from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from lobby.games.service import RoomCreationError
from lobby.server.app import create_app
from lobby.server.settings import LobbyServerSettings
from shared.auth.settings import AuthSettings


class TestLobbyViews:
    @pytest.fixture
    def client(self, tmp_path):
        config_file = tmp_path / "servers.yaml"
        config_file.write_text("""
servers:
  - name: "test-server"
    url: "http://localhost:8711"
""")
        static_dir = tmp_path / "public"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("body { color: red; }")
        app = create_app(
            settings=LobbyServerSettings(
                config_path=config_file,
                static_dir=str(static_dir),
            ),
            auth_settings=AuthSettings(
                game_ticket_secret="test-secret",
                database_path=str(tmp_path / "test.db"),
            ),
        )
        c = TestClient(app)
        # Register and login a user for authenticated view tests
        c.post(
            "/register",
            data={"username": "viewuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        return c

    def _mock_httpx_no_healthy_servers(self):
        """Patch httpx so health checks fail (no healthy servers, empty room list)."""
        patcher = patch("httpx.AsyncClient")
        mock_client = patcher.start()
        mock_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = mock_instance
        mock_instance.get.side_effect = httpx.RequestError("Connection refused")
        return patcher

    def _mock_httpx_with_rooms(self, rooms: list[dict]):
        """Patch httpx so health checks pass and list_rooms returns given rooms."""
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
        return patcher, mock_instance

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

    def test_lobby_page_returns_html(self, client):
        patcher = self._mock_httpx_no_healthy_servers()
        try:
            response = client.get("/")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            assert "Ronin Mahjong" in response.text
        finally:
            patcher.stop()

    def test_lobby_page_includes_css_link(self, client):
        patcher = self._mock_httpx_no_healthy_servers()
        try:
            response = client.get("/")
            assert "/static/styles/lobby.css" in response.text
        finally:
            patcher.stop()

    def test_lobby_page_has_no_script_tags(self, client):
        patcher = self._mock_httpx_no_healthy_servers()
        try:
            response = client.get("/")
            assert "<script" not in response.text
        finally:
            patcher.stop()

    def test_lobby_page_shows_create_room_form(self, client):
        patcher = self._mock_httpx_no_healthy_servers()
        try:
            response = client.get("/")
            assert '<form method="POST" action="/rooms/new">' in response.text
        finally:
            patcher.stop()

    def test_lobby_page_shows_refresh_link(self, client):
        patcher = self._mock_httpx_no_healthy_servers()
        try:
            response = client.get("/")
            assert '<a href="/" class="btn btn-secondary">Refresh</a>' in response.text
        finally:
            patcher.stop()

    def test_lobby_page_shows_empty_message(self, client):
        patcher = self._mock_httpx_no_healthy_servers()
        try:
            response = client.get("/")
            assert "No rooms available. Create one!" in response.text
        finally:
            patcher.stop()

    def test_lobby_page_shows_rooms(self, client):
        patcher, _ = self._mock_httpx_with_rooms(
            [
                {
                    "room_id": "abc123",
                    "player_count": 1,
                    "players_needed": 2,
                    "server_url": "http://localhost:8711",
                },
            ],
        )
        try:
            response = client.get("/")
            assert "abc123" in response.text
            assert "1/2 players" in response.text
            assert "Join" in response.text
        finally:
            patcher.stop()

    def test_lobby_page_shows_full_room(self, client):
        patcher, _ = self._mock_httpx_with_rooms(
            [
                {
                    "room_id": "full-room",
                    "player_count": 4,
                    "players_needed": 4,
                    "server_url": "http://localhost:8711",
                },
            ],
        )
        try:
            response = client.get("/")
            assert "full-room" in response.text
            assert "Full" in response.text
        finally:
            patcher.stop()

    def test_create_room_redirects_with_game_ticket(self, client):
        patcher = self._mock_httpx_for_create()
        try:
            response = client.post(
                "/rooms/new",
                follow_redirects=False,
            )
            assert response.status_code == 303
            location = response.headers["location"]
            assert location.startswith("http://localhost:8712/")
            assert "ws_url=" in location
            assert "game_ticket=" in location
        finally:
            patcher.stop()

    def test_create_room_failure_shows_error_with_rooms(self, client):
        """On creation failure, re-renders lobby with error message and existing rooms."""
        rooms = [
            {
                "room_id": "existing-room",
                "player_count": 1,
                "players_needed": 2,
                "server_url": "http://localhost:8711",
                "server_name": "test-server",
            },
        ]
        with (
            patch.object(
                client.app.state.games_service,
                "create_room",
                side_effect=RoomCreationError("No healthy game servers available"),
            ),
            patch.object(
                client.app.state.games_service,
                "list_rooms",
                return_value=rooms,
            ),
        ):
            response = client.post("/rooms/new")
            assert response.status_code == 200
            assert "No healthy game servers" in response.text
            assert "existing-room" in response.text

    def test_static_css_served(self, client):
        response = client.get("/static/styles/lobby.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]
