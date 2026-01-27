from unittest.mock import AsyncMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app


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
        app = create_app(config_path=config_file)
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

    def test_create_game_success(self, client):
        # Mock the httpx client to simulate game server responses
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_health_response = AsyncMock()
        mock_health_response.status_code = 200
        mock_create_response = AsyncMock()
        mock_create_response.status_code = 201

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            # Health check returns 200
            mock_instance.get.return_value = mock_health_response
            # Room creation returns 201
            mock_instance.post.return_value = mock_create_response

            response = client.post("/games")

            assert response.status_code == 201
            data = response.json()
            assert "room_id" in data
            assert "websocket_url" in data
            assert data["server_name"] == "test-server"
            assert "ws://localhost:8001/ws/" in data["websocket_url"]

    def test_create_game_no_healthy_servers(self, client):
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            # Health check fails with httpx.RequestError
            mock_instance.get.side_effect = httpx.RequestError("Connection refused")

            response = client.post("/games")

            assert response.status_code == 503
            assert "No healthy game servers" in response.json()["error"]
