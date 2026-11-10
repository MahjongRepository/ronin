import json
import re
from contextlib import ExitStack

import httpx
import pytest
from starlette.websockets import WebSocketDisconnect

from lobby.auth.csrf import CSRF_COOKIE_NAME
from lobby.tests.integration.conftest import login_with_csrf, register_with_csrf, session_user_id


@pytest.fixture
def busy_user_ids():
    return set()


@pytest.fixture
def app(make_app, busy_user_ids):
    async def is_playing(user_id):
        return user_id in busy_user_ids

    return make_app(is_playing=is_playing)


def _issue_api_token(client):
    client.get("/settings")
    issued = client.post("/settings/api-token", data={"csrf_token": client.cookies.get(CSRF_COOKIE_NAME)})
    match = re.search(r'id="api-token" value="([^"]+)"', issued.text)
    assert match, "the settings page shows no API token"
    return match.group(1)


def _receive_until(ws, message_type):
    while True:
        message = ws.receive_json()
        if message["type"] == message_type:
            return message


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


def test_start_games__when_tables_have_absent_and_busy_players__should_start_other_and_report_in_order(
    client, tournament_id, game_server, busy_user_ids
):
    owner_key = _issue_api_token(client)
    game_requests = []

    def create_game(request):
        game_requests.append(request)
        return httpx.Response(201)

    game_server.respond = create_game

    with ExitStack() as stack:
        sockets = {}
        for name in ["erin", "frank", "gina", "hank", "dave"]:
            register_with_csrf(client, name)
            sockets[name] = stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}"))
            sockets[name].receive_json()
        busy_user_ids.add(session_user_id(client))
        client.cookies.delete("session_id")

        response = client.post(
            f"/api/tournaments/{tournament_id}/games",
            json={
                "games": [
                    ["erin", "frank", "gina", "ghost"],
                    ["erin", "frank", "gina", "dave"],
                    ["hank", "gina", "frank", "erin"],
                ]
            },
            headers={"x-api-key": owner_key},
        )

        [create_request] = game_requests
        game_id = json.loads(create_request.content)["game_id"]
        assert response.status_code == 200
        assert response.json() == {
            "results": [
                {"error": "players_not_online", "players": ["ghost"]},
                {"error": "players_in_game", "players": ["dave"]},
                {"game_id": game_id, "players": ["hank", "gina", "frank", "erin"]},
            ]
        }
        create_body = json.loads(create_request.content)
        assert create_body["fixed_seats"] is True
        assert [player["name"] for player in create_body["players"]] == ["hank", "gina", "frank", "erin"]
        for name in ["erin", "frank", "gina", "hank"]:
            assert _receive_until(sockets[name], "game_starting")["game_id"] == game_id
        assert _receive_until(sockets["dave"], "game_started") == {
            "type": "game_started",
            "game_id": game_id,
            "players": ["hank", "gina", "frank", "erin"],
        }
        assert sockets["dave"].receive_json() == {"type": "presence", "players": ["dave"], "count": 1}

        snapshot = client.get(f"/api/tournaments/{tournament_id}", headers={"x-api-key": owner_key}).json()

    [game] = snapshot["games"]
    assert snapshot["online"] == ["dave"]
    assert game["game_id"] == game_id
    assert game["players"] == ["hank", "gina", "frank", "erin"]
    assert (game["ended_at"], game["end_reason"], game["result"]) == (None, None, None)


def test_start_games__when_called_with_cookie_only__should_return_401(client, tournament_id):
    response = client.post(
        f"/api/tournaments/{tournament_id}/games", json={"games": [["erin", "frank", "gina", "hank"]]}
    )

    assert response.status_code == 401


def test_start_games__when_caller_is_not_owner__should_return_404(client, tournament_id):
    login_with_csrf(client, "bob")
    bob_key = _issue_api_token(client)
    client.cookies.delete("session_id")

    response = client.post(
        f"/api/tournaments/{tournament_id}/games",
        json={"games": [["erin", "frank", "gina", "hank"]]},
        headers={"x-api-key": bob_key},
    )

    assert response.status_code == 404
    assert response.json() == {"error": "tournament_not_found"}


def test_events_socket__when_owner_connects_with_api_key__should_receive_game_started(
    client, tournament_id, game_server
):
    owner_key = _issue_api_token(client)
    game_server.respond = lambda request: httpx.Response(201)
    names = ["erin", "frank", "gina", "hank"]

    with ExitStack() as stack:
        for name in names:
            register_with_csrf(client, name)
            stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}")).receive_json()
        client.cookies.delete("session_id")
        del client.headers["origin"]

        events = stack.enter_context(
            client.websocket_connect(f"/ws/tournaments/{tournament_id}/events", headers={"x-api-key": owner_key})
        )
        assert events.receive_json() == {"type": "presence", "players": names, "count": 4}

        response = client.post(
            f"/api/tournaments/{tournament_id}/games", json={"games": [names]}, headers={"x-api-key": owner_key}
        )

        [result] = response.json()["results"]
        assert events.receive_json() == {"type": "game_started", "game_id": result["game_id"], "players": names}
        assert events.receive_json() == {"type": "presence", "players": [], "count": 0}


def test_events_socket__when_user_is_not_owner__should_be_refused(client, tournament_id):
    login_with_csrf(client, "bob")

    with client.websocket_connect(f"/ws/tournaments/{tournament_id}/events") as events:
        assert events.receive_json() == {"type": "error", "message": "tournament_not_found"}
        with pytest.raises(WebSocketDisconnect) as refusal:
            events.receive_json()

    assert refusal.value.code == 4000
