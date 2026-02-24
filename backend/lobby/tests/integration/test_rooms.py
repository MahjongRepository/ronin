"""Integration tests for lobby endpoints with local room management."""

import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.server.settings import LobbyServerSettings
from shared.auth.settings import AuthSettings


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
            auth_settings=AuthSettings(
                game_ticket_secret="test-secret",
                database_path=str(tmp_path / "test.db"),
            ),
        )
        c = TestClient(app)
        # Register a user so authenticated endpoints can be tested
        c.post(
            "/register",
            data={"username": "apiuser", "password": "securepass123", "confirm_password": "securepass123"},
        )
        yield c
        app.state.db.close()

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "commit" in data

    def test_list_servers(self, client):
        response = client.get("/servers")
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data
        assert len(data["servers"]) == 1
        assert data["servers"][0]["name"] == "test-server"

    def test_old_rooms_endpoints_not_found(self, client):
        """Old /rooms JSON API endpoints no longer exist."""
        response = client.get("/rooms")
        assert response.status_code in {404, 303}  # 303 redirect for /rooms -> room_page or 404

    def test_old_games_endpoints_not_found(self, client):
        """Old /games endpoints no longer exist."""
        response = client.get("/games")
        assert response.status_code == 404

        response = client.post("/games")
        assert response.status_code == 404
