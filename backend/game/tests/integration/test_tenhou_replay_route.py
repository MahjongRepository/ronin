import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from game.replay.external.tenhou import convert_replay
from game.server.app import create_app
from game.server.settings import GameServerSettings
from game.tests.helpers.session import make_session_manager
from game.wire.enums import WireEventType
from shared.storage import LocalReplayStorage

FULL_GAME_REPLAY = Path(__file__).parent / "replays" / "fixtures" / "full_round" / "full_game.txt"
STORED_GAME_ID = "stored-game"
FAILED_GAME_ID = "failed-game"


def _without_game_end(replay: str) -> str:
    return "\n".join(line for line in replay.splitlines() if json.loads(line).get("t") != WireEventType.GAME_END)


@pytest.fixture
def client(tmp_path):
    storage = LocalReplayStorage(str(tmp_path))
    storage.save_replay(STORED_GAME_ID, FULL_GAME_REPLAY.read_text())
    storage.save_replay(FAILED_GAME_ID, _without_game_end(FULL_GAME_REPLAY.read_text()))
    session_manager = make_session_manager()
    app = create_app(
        settings=GameServerSettings(replay_dir=str(tmp_path)),
        game_service=session_manager._game_service,
        session_manager=session_manager,
    )
    with TestClient(app) as client:
        yield client


def _internal_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.app.state.settings.internal_api_secret}"}


def test_tenhou_replay_route__when_replay_is_stored__should_answer_its_tenhou_xml(client):
    response = client.get(f"/replays/{STORED_GAME_ID}/tenhou", headers=_internal_headers(client))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml"
    assert response.text == convert_replay(FULL_GAME_REPLAY)

    missing = client.get("/replays/missing-game/tenhou", headers=_internal_headers(client))
    assert missing.status_code == 404


def test_tenhou_replay_route__when_replay_is_a_failed_games__should_answer_422_not_a_truncated_log(client):
    response = client.get(f"/replays/{FAILED_GAME_ID}/tenhou", headers=_internal_headers(client))
    assert response.status_code == 422
    assert response.json() == {"error": "Replay has no game end"}


def test_tenhou_replay_route__when_caller_lacks_the_internal_secret__should_answer_401(client):
    response = client.get(f"/replays/{STORED_GAME_ID}/tenhou", headers={"Authorization": "Bearer wrong-secret"})
    assert response.status_code == 401
