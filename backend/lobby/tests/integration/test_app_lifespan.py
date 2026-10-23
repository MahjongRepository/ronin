import asyncio

import pytest
from starlette.testclient import TestClient

from lobby.rooms.manager import LobbyRoomManager


def _assert_database_closed(app) -> None:
    with pytest.raises(RuntimeError, match="not open"):
        asyncio.run(app.state.game_repo.get_recent_games())


class TestLobbyLifespan:
    def test_lobby_lifespan__when_startup_step_fails__should_close_database_and_stop_cleanup(self, app, monkeypatch):
        def fail_to_start_reaper(_self):
            raise RuntimeError("reaper failed to start")

        monkeypatch.setattr(LobbyRoomManager, "start_reaper", fail_to_start_reaper)

        with pytest.raises(RuntimeError, match="reaper failed to start"), TestClient(app):
            pass

        _assert_database_closed(app)
        assert app.state.auth_service._session_store._cleanup_task is None

    def test_lobby_lifespan__when_reaper_died__should_still_close_database(self, app, monkeypatch):
        async def crashing_reaper_loop(_self):
            raise RuntimeError("reaper crashed")

        monkeypatch.setattr(LobbyRoomManager, "_reaper_loop", crashing_reaper_loop)

        with TestClient(app) as client:
            assert client.get("/health").status_code == 200

        _assert_database_closed(app)
