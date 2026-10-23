import pytest
from starlette.testclient import TestClient

from lobby.server.app import create_app
from lobby.settings import LobbyServerSettings
from lobby.tests.integration.conftest import register_with_csrf
from shared.auth.settings import AuthSettings


class TestLobbyEndpoints:
    @pytest.fixture
    def client(self, tmp_path):
        static_dir = tmp_path / "public"
        (static_dir / "styles").mkdir(parents=True)
        (static_dir / "styles" / "lobby.css").write_text("/* test */")

        app = create_app(
            settings=LobbyServerSettings(
                static_dir=str(static_dir),
            ),
            auth_settings=AuthSettings(
                game_ticket_secret="test-secret",
                database_path=str(tmp_path / "test.db"),
                cookie_secure=False,
            ),
        )
        with TestClient(app) as c:
            # Register a user so authenticated endpoints can be tested
            register_with_csrf(c, "apiuser")
            yield c

    def test_health_route__should_return_ok_with_version_and_commit(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "commit" in data
