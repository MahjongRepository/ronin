from unittest.mock import AsyncMock, MagicMock, patch

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
            # health check returns 200
            mock_instance.get.return_value = mock_health_response
            # game creation returns 201
            mock_instance.post.return_value = mock_create_response

            response = client.post("/games")

            assert response.status_code == 201
            data = response.json()
            assert "game_id" in data
            assert "websocket_url" in data
            assert data["server_name"] == "test-server"
            assert "ws://localhost:8001/ws/" in data["websocket_url"]

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


class TestStaticFiles:
    @pytest.fixture
    def client(self, tmp_path):
        config_file = tmp_path / "servers.yaml"
        config_file.write_text("""
servers:
  - name: "test-server"
    url: "http://localhost:8001"
""")
        app = create_app(config_path=config_file)
        return TestClient(app)

    def test_root_redirects_to_static_index(self, client):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/static/index.html"

    def test_static_index_html_served(self, client):
        response = client.get("/static/index.html")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Ronin Lobby" in response.text

    def test_root_redirect_follows_to_index(self, client):
        response = client.get("/", follow_redirects=True)
        assert response.status_code == 200
        assert "Ronin Lobby" in response.text
