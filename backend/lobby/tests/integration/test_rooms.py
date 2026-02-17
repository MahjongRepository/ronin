from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.server.settings import LobbyServerSettings


class TestLobbyEndpoints:
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
        (static_dir / "styles" / "lobby.css").write_text("/* test */")
        app = create_app(
            settings=LobbyServerSettings(
                config_path=config_file,
                static_dir=str(static_dir),
            ),
        )
        return TestClient(app)

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_list_servers(self, client):
        response = client.get("/servers")
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data
        assert len(data["servers"]) == 1
        assert data["servers"][0]["name"] == "test-server"

    def _mock_httpx_for_create(self):
        """Return a patch context manager that mocks httpx for room creation."""
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
        return patcher, mock_instance

    def test_create_room_success(self, client):
        patcher, _mock_instance = self._mock_httpx_for_create()
        try:
            response = client.post("/rooms")

            assert response.status_code == 201
            data = response.json()
            assert "room_id" in data
            assert "websocket_url" in data
            assert data["server_name"] == "test-server"
            assert "ws://localhost:8711/ws/" in data["websocket_url"]
        finally:
            patcher.stop()

    def test_create_room_with_num_ai_players(self, client):
        patcher, mock_instance = self._mock_httpx_for_create()
        try:
            response = client.post("/rooms", json={"num_ai_players": 2})

            assert response.status_code == 201
            call_args = mock_instance.post.call_args
            assert call_args[1]["json"]["num_ai_players"] == 2
        finally:
            patcher.stop()

    def test_create_room_no_body_defaults_to_3_ai_players(self, client):
        patcher, mock_instance = self._mock_httpx_for_create()
        try:
            response = client.post("/rooms")

            assert response.status_code == 201
            call_args = mock_instance.post.call_args
            assert call_args[1]["json"]["num_ai_players"] == 3
        finally:
            patcher.stop()

    def test_create_room_invalid_num_ai_players(self, client):
        response = client.post("/rooms", json={"num_ai_players": 5})
        assert response.status_code == 422
        assert "error" in response.json()

        response = client.post("/rooms", json={"num_ai_players": -1})
        assert response.status_code == 422
        assert "error" in response.json()

    def test_create_room_legacy_num_bots_rejected(self, client):
        """Legacy payload with num_bots is rejected (extra=forbid)."""
        response = client.post("/rooms", json={"num_bots": 2})
        assert response.status_code == 422
        assert "error" in response.json()

    def test_create_room_malformed_json_rejected(self, client):
        """Malformed JSON body returns 422 instead of falling back to defaults."""
        response = client.post(
            "/rooms",
            content='{"num_ai_players": 2',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert "error" in response.json()

    def test_create_room_non_object_json_body(self, client):
        """Non-object JSON (null, array) returns 422 instead of 500."""
        response = client.post("/rooms", content="null", headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert "error" in response.json()

        response = client.post("/rooms", content="[1,2]", headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert "error" in response.json()

    def test_create_room_no_healthy_servers(self, client):
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.RequestError("Connection refused")

            response = client.post("/rooms")

            assert response.status_code == 503
            assert "No healthy game servers" in response.json()["error"]

    def test_list_rooms_success(self, client):
        mock_health_response = MagicMock()
        mock_health_response.status_code = 200

        mock_rooms_response = MagicMock()
        mock_rooms_response.status_code = 200
        mock_rooms_response.json.return_value = {
            "rooms": [
                {
                    "room_id": "abc123",
                    "player_count": 2,
                    "players_needed": 3,
                    "total_seats": 4,
                    "num_ai_players": 1,
                    "players": ["Alice", "Bob"],
                },
            ],
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            def get_side_effect(url):
                if "/health" in url:
                    return mock_health_response
                if "/rooms" in url:
                    return mock_rooms_response
                return mock_health_response

            mock_instance.get.side_effect = get_side_effect

            response = client.get("/rooms")

            assert response.status_code == 200
            data = response.json()
            assert "rooms" in data
            assert len(data["rooms"]) == 1
            room = data["rooms"][0]
            assert room["room_id"] == "abc123"
            assert room["player_count"] == 2
            assert room["players_needed"] == 3
            assert room["total_seats"] == 4
            assert room["num_ai_players"] == 1
            assert room["players"] == ["Alice", "Bob"]
            assert room["server_name"] == "test-server"
            assert room["server_url"] == "http://localhost:8711"

    def test_list_rooms_empty_when_no_healthy_servers(self, client):
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.RequestError("Connection refused")

            response = client.get("/rooms")

            assert response.status_code == 200
            data = response.json()
            assert data == {"rooms": []}

    def test_old_games_endpoints_not_found(self, client):
        """Old /games endpoints no longer exist."""
        response = client.get("/games")
        assert response.status_code == 404

        response = client.post("/games")
        assert response.status_code == 404
