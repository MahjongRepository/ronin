import pytest

from lobby.tests.integration.conftest import register_with_csrf


class TestLobbyEndpoints:
    @pytest.fixture
    def client(self, client):
        register_with_csrf(client, "apiuser")
        return client

    def test_health_route__should_return_ok_with_version_and_commit(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "commit" in data
