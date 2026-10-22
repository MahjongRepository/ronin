import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from game.server.app import create_app
from game.server.settings import GameServerSettings
from game.tests.mocks import MockGameService
from shared.dal.models import PlayedGame


def _assert_database_closed(app) -> None:
    with pytest.raises(RuntimeError, match="not open"):
        app.state.session_manager._game_repository._db.submit_read(lambda conn: conn.execute("SELECT 1"))


class TestOwnedDbShutdown:
    def test_app_shutdown__when_app_owns_db__should_drain_posted_writes_and_close_it(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("AUTH_DATABASE_PATH", str(db_path))
        app = create_app(settings=GameServerSettings(), game_service=MockGameService())

        with TestClient(app):
            app.state.session_manager._game_repository.create_game(
                PlayedGame(game_id="game1", started_at=datetime.now(UTC)),
            )

        _assert_database_closed(app)
        with closing(sqlite3.connect(db_path)) as conn:
            assert conn.execute("SELECT id FROM played_games").fetchall() == [("game1",)]

    def test_app_startup__when_opening_db_fails_midway__should_raise_and_leave_it_closed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUTH_DATABASE_PATH", str(tmp_path / "test.db"))

        def fail_to_harden_permissions(_self):
            raise OSError("chmod refused")

        app = create_app(settings=GameServerSettings(), game_service=MockGameService())
        db = app.state.session_manager._game_repository._db
        monkeypatch.setattr(type(db), "_harden_permissions", fail_to_harden_permissions)

        with pytest.raises(OSError, match="chmod refused"), TestClient(app):
            pass

        _assert_database_closed(app)
