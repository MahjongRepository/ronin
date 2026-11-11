import json
import re
from contextlib import ExitStack
from datetime import UTC, datetime
from unittest.mock import ANY

import httpx
import pytest
from starlette.websockets import WebSocketDisconnect

from lobby.auth.csrf import CSRF_COOKIE_NAME
from lobby.tests.integration.conftest import login_with_csrf, register_with_csrf, session_user_id
from shared.dal.models import GameEndReason, PlayedGame, PlayedGameStanding, TournamentGame


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
        assert _receive_until(ws_alice, "joined") == {"type": "joined", "players": ["alice"]}

        login_with_csrf(client, "bob")
        with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_bob:
            assert _receive_until(ws_bob, "joined") == {"type": "joined", "players": ["alice", "bob"]}
            assert ws_alice.receive_json() == {"type": "presence", "players": ["alice", "bob"], "count": 2}

        assert ws_alice.receive_json() == {"type": "presence", "players": ["alice"], "count": 1}


def test_tournament_chat__when_user_sends_message__should_broadcast_to_all(client, tournament_id):
    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice:
        _receive_until(ws_alice, "joined")
        login_with_csrf(client, "bob")
        with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_bob:
            _receive_until(ws_bob, "joined")
            ws_alice.receive_json()

            ws_bob.send_text(json.dumps({"type": "chat", "text": "good luck"}))

            expected = {"type": "chat", "player_name": "bob", "text": "good luck", "time": ANY}
            assert ws_bob.receive_json() == expected
            assert ws_alice.receive_json() == expected


def test_tournament_socket__when_users_join_after_chat__should_get_history_without_own_presence(client, tournament_id):
    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice:
        _receive_until(ws_alice, "joined")
        ws_alice.send_text(json.dumps({"type": "chat", "text": "who is here?"}))
        ws_alice.receive_json()

    login_with_csrf(client, "bob")
    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_bob:
        bob_history = ws_bob.receive_json()
        bob_joined = ws_bob.receive_json()

    login_with_csrf(client, "alice")
    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice:
        alice_history = ws_alice.receive_json()

    chat = {"type": "chat", "player_name": "alice", "text": "who is here?", "time": ANY}
    assert bob_history == {
        "type": "history",
        "messages": [
            {"type": "player_online", "player_name": "alice", "time": ANY},
            chat,
            {"type": "player_offline", "player_name": "alice", "time": ANY},
        ],
    }
    assert bob_joined == {"type": "joined", "players": ["bob"]}
    assert alice_history["messages"] == [
        chat,
        {"type": "player_online", "player_name": "bob", "time": ANY},
        {"type": "player_offline", "player_name": "bob", "time": ANY},
    ]


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


def test_start_games__when_a_table_repeats_a_name__should_return_400_and_start_nothing(
    client, tournament_id, game_server
):
    owner_key = _issue_api_token(client)
    game_requests = []

    def create_game(request):
        game_requests.append(request)
        return httpx.Response(201)

    game_server.respond = create_game

    with ExitStack() as stack:
        for name in ["erin", "frank", "gina", "hank"]:
            register_with_csrf(client, name)
            stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}")).receive_json()
        client.cookies.delete("session_id")

        response = client.post(
            f"/api/tournaments/{tournament_id}/games",
            json={"games": [["erin", "frank", "gina", "hank"], ["erin", "frank", "gina", "erin"]]},
            headers={"x-api-key": owner_key},
        )
        snapshot = client.get(f"/api/tournaments/{tournament_id}", headers={"x-api-key": owner_key}).json()

    assert response.status_code == 400
    assert set(response.json()) == {"error"}
    assert game_requests == []
    assert snapshot["games"] == []


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


def test_game_end_poll__when_played_game_gains_ended_at__should_update_row_and_publish_once(
    app, client, tournament_id, game_server
):
    owner_key = _issue_api_token(client)
    game_server.respond = lambda request: httpx.Response(201)
    names = ["erin", "frank", "gina", "hank"]
    ended_at = datetime(2026, 11, 11, 12, 30, tzinfo=UTC)
    standings_by_placement = [
        PlayedGameStanding(name="gina", seat=2, score=41000, final_score=51),
        PlayedGameStanding(name="erin", seat=0, score=28000, final_score=8),
        PlayedGameStanding(name="hank", seat=3, score=19000, final_score=-21),
        PlayedGameStanding(name="frank", seat=1, score=12000, final_score=-38),
    ]
    expected_result = [standing.model_dump(mode="json") for standing in standings_by_placement]
    expected_event_result = [
        standing.model_dump(mode="json", exclude={"user_id"}) for standing in standings_by_placement
    ]

    with ExitStack() as stack:
        for name in names:
            register_with_csrf(client, name)
            stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}")).receive_json()
        register_with_csrf(client, "dave")
        dave = stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}"))
        dave.receive_json()
        client.cookies.delete("session_id")
        events = stack.enter_context(
            client.websocket_connect(f"/ws/tournaments/{tournament_id}/events", headers={"x-api-key": owner_key})
        )
        events.receive_json()

        response = client.post(
            f"/api/tournaments/{tournament_id}/games", json={"games": [names]}, headers={"x-api-key": owner_key}
        )
        [result] = response.json()["results"]
        game_id = result["game_id"]
        for ws in (dave, events):
            _receive_until(ws, "game_started")
            ws.receive_json()

        app.state.game_repo.finish_game(
            PlayedGame(
                game_id=game_id,
                started_at=datetime(2026, 11, 11, 12, 0, tzinfo=UTC),
                ended_at=ended_at,
                end_reason=GameEndReason.COMPLETED,
                standings=standings_by_placement,
            )
        )
        client.portal.call(app.state.tournament_game_end_poller.poll_once)
        client.portal.call(app.state.tournament_game_end_poller.poll_once)
        register_with_csrf(client, "ivan")
        ivan_history = stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}")).receive_json()
        client.cookies.delete("session_id")

        expected_event = {
            "type": "game_ended",
            "game_id": game_id,
            "players": names,
            "end_reason": "completed",
            "result": expected_event_result,
        }
        for ws in (dave, events):
            assert ws.receive_json() == expected_event
            assert ws.receive_json() == {"type": "presence", "players": ["dave", "ivan"], "count": 2}
        game_entries = [entry for entry in ivan_history["messages"] if entry["type"] in ("game_started", "game_ended")]
        offline_entries = [entry for entry in ivan_history["messages"] if entry["type"] == "player_offline"]
        assert game_entries == [
            {"type": "game_started", "game_id": game_id, "players": names, "time": ANY},
            {**expected_event, "time": ANY},
        ]
        assert offline_entries == []

        snapshot = client.get(f"/api/tournaments/{tournament_id}", headers={"x-api-key": owner_key}).json()

    [game] = snapshot["games"]
    assert game["ended_at"] == ended_at.timestamp()
    assert game["end_reason"] == "completed"
    assert game["result"] == expected_result


def test_events_socket__when_user_is_not_owner__should_be_refused(client, tournament_id):
    login_with_csrf(client, "bob")

    with client.websocket_connect(f"/ws/tournaments/{tournament_id}/events") as events:
        assert events.receive_json() == {"type": "error", "message": "tournament_not_found"}
        with pytest.raises(WebSocketDisconnect) as refusal:
            events.receive_json()

    assert refusal.value.code == 4000


def test_events_socket__when_key_is_invalid_and_origin_missing__should_close_unauthenticated(client, tournament_id):
    client.cookies.delete("session_id")
    del client.headers["origin"]

    with (
        pytest.raises(WebSocketDisconnect) as refusal,
        client.websocket_connect(f"/ws/tournaments/{tournament_id}/events", headers={"x-api-key": "bogus"}),
    ):
        pass

    assert refusal.value.code == 4001


def test_game_exit__when_game_belongs_to_tournament__should_redirect_to_tournament_page(app, client, tournament_id):
    tournament_game = TournamentGame(
        game_id="cup-game-1",
        tournament_id=tournament_id,
        players=["erin", "frank", "gina", "hank"],
        created_at=datetime(2026, 11, 11, 12, 0, tzinfo=UTC).timestamp(),
    )
    client.portal.call(app.state.tournament_repo.add_game, tournament_game)

    response = client.get("/games/cup-game-1/exit", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/tournaments/{tournament_id}"


def test_game_exit__when_game_is_not_tournament__should_redirect_to_lobby(client, tournament_id):
    response = client.get("/games/room-game-1/exit", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_tournament_delete__when_owner_deletes__should_close_sockets_and_return_404(app, client, tournament_id):
    owner_key = _issue_api_token(client)
    csrf = client.cookies.get(CSRF_COOKIE_NAME)
    tournament_game = TournamentGame(
        game_id="cup-game-1",
        tournament_id=tournament_id,
        players=["erin", "frank", "gina", "hank"],
        created_at=datetime(2026, 11, 11, 12, 0, tzinfo=UTC).timestamp(),
    )
    client.portal.call(app.state.tournament_repo.add_game, tournament_game)

    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice:
        _receive_until(ws_alice, "joined")

        deleted = client.post(f"/tournaments/{tournament_id}/delete", data={"csrf_token": csrf}, follow_redirects=False)

        assert ws_alice.receive_json() == {"type": "error", "message": "tournament_deleted"}
        with pytest.raises(WebSocketDisconnect) as closed:
            ws_alice.receive_json()

    assert (deleted.status_code, deleted.headers["location"]) == (303, "/")
    assert closed.value.code == 4000
    assert client.get(f"/tournaments/{tournament_id}").status_code == 404
    game_exit = client.get("/games/cup-game-1/exit", follow_redirects=False)
    assert (game_exit.status_code, game_exit.headers["location"]) == (303, "/")
    client.cookies.delete("session_id")
    assert client.get(f"/api/tournaments/{tournament_id}", headers={"x-api-key": owner_key}).status_code == 404


def test_tournament_delete__when_user_is_not_owner__should_return_404(client, tournament_id):
    login_with_csrf(client, "bob")
    client.get(f"/tournaments/{tournament_id}")

    refused = client.post(
        f"/tournaments/{tournament_id}/delete", data={"csrf_token": client.cookies.get(CSRF_COOKIE_NAME)}
    )

    assert refused.status_code == 404
    assert client.get(f"/tournaments/{tournament_id}").status_code == 200
