import logging

import httpx
import pytest

from tests.integration.conftest import login_with_csrf, register_with_csrf


def _game(game_id, players):
    return {"game_id": game_id, "started_at": 1_700_000_000.0, "game_type": "hanchan", "players": players}


@pytest.fixture
def app(make_app):
    return make_app(playing_games_poll_interval=3600)


def test_playing_games_socket__when_games_start_end_and_lookup_fails__should_push_each_changed_list_once(
    client, game_server, caplog
):
    first = _game("g1", ["A", "B", "C", "D"])
    second = _game("g2", ["E", "F", "G", "H"])
    games = [first]

    def answer(request):
        if games is None:
            raise httpx.ConnectError("game server down", request=request)

        assert request.headers["authorization"] == f"Bearer {client.app.state.settings.internal_api_secret}"
        return httpx.Response(200, json={"games": games})

    game_server.respond = answer
    feed = client.app.state.playing_games_feed
    register_with_csrf(client, "alice")

    with client.websocket_connect("/ws/games") as alice:
        assert alice.receive_json() == {"type": "games", "games": [first]}

        games = [first, second]
        client.portal.call(feed.poll_once)
        client.portal.call(feed.poll_once)
        assert alice.receive_json() == {"type": "games", "games": [first, second]}

        login_with_csrf(client, "bob")
        with client.websocket_connect("/ws/games") as bob:
            assert bob.receive_json() == {"type": "games", "games": [first, second]}

        games = None
        with caplog.at_level(logging.WARNING):
            client.portal.call(feed.poll_once)
            client.portal.call(feed.poll_once)
        games = [second]
        client.portal.call(feed.poll_once)
        assert alice.receive_json() == {"type": "games", "games": [second]}

    lookup_warnings = [record for record in caplog.records if "playing games lookup failed" in record.getMessage()]
    assert len(lookup_warnings) == 1
