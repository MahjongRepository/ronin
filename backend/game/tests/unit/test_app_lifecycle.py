"""Tests for game server app lifecycle (DB ownership and shutdown)."""

from starlette.testclient import TestClient

from game.server.app import create_app
from game.server.settings import GameServerSettings
from game.tests.mocks import MockGameService


class TestOwnedDbShutdown:
    def test_shutdown_closes_owned_db(self, tmp_path, monkeypatch):
        """When the app creates its own SessionManager, shutdown closes the owned DB."""
        monkeypatch.setenv("GAME_DATABASE_PATH", str(tmp_path / "test.db"))
        settings = GameServerSettings()
        app = create_app(settings=settings, game_service=MockGameService())

        with TestClient(app):
            db = app.state.session_manager._game_repository._db
            assert db.connection is not None

        assert db._conn is None
