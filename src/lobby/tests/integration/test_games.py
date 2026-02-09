from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.server.settings import LobbyServerSettings


class TestLobbyEndpoints:
    @pytest.fixture
    def client(self, tmp_path):
        # Create test config
        config_file = tmp_path / "servers.yaml"
        config_file.write_text("""
servers:
  - name: "test-server"
    url: "http://localhost:8001"
""")
        app = create_app(settings=LobbyServerSettings(config_path=config_file))
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
        """
        Return a patch context manager that mocks httpx for game creation.
        """
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

    def test_create_game_success(self, client):
        patcher, _mock_instance = self._mock_httpx_for_create()
        try:
            response = client.post("/games")

            assert response.status_code == 201
            data = response.json()
            assert "game_id" in data
            assert "websocket_url" in data
            assert data["server_name"] == "test-server"
            assert "ws://localhost:8001/ws/" in data["websocket_url"]
        finally:
            patcher.stop()

    def test_create_game_with_num_bots(self, client):
        patcher, mock_instance = self._mock_httpx_for_create()
        try:
            response = client.post("/games", json={"num_bots": 2})

            assert response.status_code == 201
            # verify num_bots=2 was passed to the game server
            call_args = mock_instance.post.call_args
            assert call_args[1]["json"]["num_bots"] == 2
        finally:
            patcher.stop()

    def test_create_game_no_body_defaults_to_3_bots(self, client):
        patcher, mock_instance = self._mock_httpx_for_create()
        try:
            response = client.post("/games")

            assert response.status_code == 201
            # verify num_bots=3 (default) was passed to the game server
            call_args = mock_instance.post.call_args
            assert call_args[1]["json"]["num_bots"] == 3
        finally:
            patcher.stop()

    def test_create_game_invalid_num_bots(self, client):
        # Above max (le=3)
        response = client.post("/games", json={"num_bots": 5})
        assert response.status_code == 422
        assert "error" in response.json()

        # Below min (ge=0)
        response = client.post("/games", json={"num_bots": -1})
        assert response.status_code == 422
        assert "error" in response.json()

    def test_create_game_non_object_json_body(self, client):
        """Non-object JSON (null, array) returns 422 instead of 500."""
        response = client.post("/games", content="null", headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert "error" in response.json()

        response = client.post("/games", content="[1,2]", headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert "error" in response.json()

    def test_create_game_no_healthy_servers(self, client):
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            # health check fails with httpx.RequestError
            mock_instance.get.side_effect = httpx.RequestError("Connection refused")

            response = client.post("/games")

            assert response.status_code == 503
            assert "No healthy game servers" in response.json()["error"]

    def test_list_games_success(self, client):
        mock_health_response = MagicMock()
        mock_health_response.status_code = 200

        mock_games_response = MagicMock()
        mock_games_response.status_code = 200
        mock_games_response.json.return_value = {
            "games": [
                {"game_id": "abc123", "player_count": 2, "max_players": 4},
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            def get_side_effect(url):
                if "/health" in url:
                    return mock_health_response
                if "/games" in url:
                    return mock_games_response
                return mock_health_response

            mock_instance.get.side_effect = get_side_effect

            response = client.get("/games")

            assert response.status_code == 200
            data = response.json()
            assert "games" in data
            assert len(data["games"]) == 1
            assert data["games"][0]["game_id"] == "abc123"
            assert data["games"][0]["server_name"] == "test-server"
            assert data["games"][0]["server_url"] == "http://localhost:8001"

    def test_list_games_empty_when_no_healthy_servers(self, client):
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.RequestError("Connection refused")

            response = client.get("/games")

            assert response.status_code == 200
            data = response.json()
            assert data == {"games": []}
