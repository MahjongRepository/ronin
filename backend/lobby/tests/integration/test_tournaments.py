import json

import pytest

from lobby.auth.csrf import CSRF_COOKIE_NAME
from lobby.tests.integration.conftest import login_with_csrf, register_with_csrf


@pytest.fixture
def tournament_id(client):
    register_with_csrf(client, "bob")
    register_with_csrf(client, "alice")
    client.get("/")
    created = client.post("/tournaments/new", data={"name": "Cup", "csrf_token": client.cookies.get(CSRF_COOKIE_NAME)})
    return created.url.path.rsplit("/", 1)[1]


def test_tournament_socket__when_second_user_connects__should_show_both_in_presence(client, tournament_id):
    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice:
        assert ws_alice.receive_json() == {"type": "joined", "players": ["alice"]}

        login_with_csrf(client, "bob")
        with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_bob:
            assert ws_bob.receive_json() == {"type": "joined", "players": ["alice", "bob"]}
            assert ws_alice.receive_json() == {"type": "presence", "players": ["alice", "bob"], "count": 2}

        assert ws_alice.receive_json() == {"type": "presence", "players": ["alice"], "count": 1}


def test_tournament_chat__when_user_sends_message__should_broadcast_to_all(client, tournament_id):
    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice:
        ws_alice.receive_json()
        login_with_csrf(client, "bob")
        with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_bob:
            ws_bob.receive_json()
            ws_alice.receive_json()

            ws_bob.send_text(json.dumps({"type": "chat", "text": "good luck"}))

            expected = {"type": "chat", "player_name": "bob", "text": "good luck"}
            assert ws_bob.receive_json() == expected
            assert ws_alice.receive_json() == expected
