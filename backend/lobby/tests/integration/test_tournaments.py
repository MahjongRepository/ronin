import json
from contextlib import ExitStack
from datetime import UTC, datetime
from unittest.mock import ANY

import httpx
import pytest
from starlette.websockets import WebSocketDisconnect

from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.dal.models import GameEndReason, PlayedGame, PlayedGameStanding, TournamentGame
from app.views import tournament_handlers
from tests.integration.conftest import (
    create_tournament,
    issue_api_token,
    login_with_csrf,
    post_lobby_json,
    register_with_csrf,
    session_user_id,
    switch_user_with_csrf,
)


@pytest.fixture(autouse=True)
def open_tournament_creation(monkeypatch):
    monkeypatch.setattr(tournament_handlers, "TOURNAMENT_CREATION_CLOSED", False)


@pytest.fixture
def busy_user_ids():
    return set()


@pytest.fixture
def app(make_app, busy_user_ids):
    async def is_playing(user_id):
        return user_id in busy_user_ids

    return make_app(is_playing=is_playing)


def _receive_until(ws, message_type):
    while True:
        message = ws.receive_json()
        if message["type"] == message_type:
            return message


@pytest.fixture
def tournament_id(client):
    register_with_csrf(client, "bob")
    register_with_csrf(client, "alice")
    return create_tournament(client)


def test_tournament_socket__when_second_user_connects_and_leaves__should_update_presence(client, tournament_id):
    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice:
        assert _receive_until(ws_alice, "joined") == {"type": "joined", "players": ["alice"], "games": [], "played": []}

        switch_user_with_csrf(client, "bob")
        with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_bob:
            assert _receive_until(ws_bob, "joined") == {
                "type": "joined",
                "players": ["alice", "bob"],
                "games": [],
                "played": [],
            }
            assert ws_alice.receive_json() == {"type": "presence", "players": ["alice", "bob"], "count": 2}

        assert ws_alice.receive_json() == {"type": "presence", "players": ["alice"], "count": 1}


def test_tournament_chat__when_user_sends_message__should_broadcast_to_all(client, tournament_id):
    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice:
        _receive_until(ws_alice, "joined")
        switch_user_with_csrf(client, "bob")
        with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_bob:
            _receive_until(ws_bob, "joined")
            _receive_until(ws_alice, "presence")

            ws_bob.send_text(json.dumps({"type": "chat", "text": "good luck"}))

            expected = {"type": "chat", "player_name": "bob", "text": "good luck", "time": ANY}
            assert ws_bob.receive_json() == expected
            assert ws_alice.receive_json() == expected


def test_tournament_socket__when_users_join_after_chat__should_get_chat_history(client, tournament_id):
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
        "messages": [chat],
    }
    assert bob_joined == {"type": "joined", "players": ["bob"], "games": [], "played": []}
    assert alice_history["messages"] == [
        chat,
    ]


def test_start_games__when_tables_have_absent_busy_and_miscased_players__should_start_other_with_canonical_names(
    client, tournament_id, game_server, busy_user_ids
):
    owner_key = issue_api_token(client)
    game_requests = []

    def create_game(request):
        game_requests.append(request)
        return httpx.Response(201)

    game_server.respond = create_game

    with ExitStack() as stack:
        sockets = {}
        for name in ["erin", "frank", "gina", "hank", "dave"]:
            client.cookies.delete("session_id")
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
                    ["Hank", "GINA", "frank", "erin"],
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


def test_start_games__when_a_table_repeats_a_name_in_another_case__should_return_400_and_start_nothing(
    client, tournament_id, game_server
):
    owner_key = issue_api_token(client)
    game_requests = []

    def create_game(request):
        game_requests.append(request)
        return httpx.Response(201)

    game_server.respond = create_game

    with ExitStack() as stack:
        for name in ["erin", "frank", "gina", "hank"]:
            client.cookies.delete("session_id")
            register_with_csrf(client, name)
            stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}")).receive_json()
        client.cookies.delete("session_id")

        response = client.post(
            f"/api/tournaments/{tournament_id}/games",
            json={"games": [["erin", "frank", "gina", "hank"], ["erin", "frank", "gina", "Erin"]]},
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
    bob_key = issue_api_token(client)
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
    owner_key = issue_api_token(client)
    game_server.respond = lambda request: httpx.Response(201)
    names = ["erin", "frank", "gina", "hank"]

    with ExitStack() as stack:
        for name in names:
            client.cookies.delete("session_id")
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


def test_game_end_poll__when_played_game_gains_ended_at__should_publish_once_and_list_it_as_played(
    app, client, tournament_id, game_server
):
    owner_key = issue_api_token(client)
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
            client.cookies.delete("session_id")
            register_with_csrf(client, name)
            stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}")).receive_json()
        client.cookies.delete("session_id")
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
        login_with_csrf(client, "erin")
        erin_joined = _receive_until(
            stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}")), "joined"
        )

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
        client.cookies.delete("session_id")
        register_with_csrf(client, "ivan")
        ivan = stack.enter_context(client.websocket_connect(f"/ws/tournaments/{tournament_id}"))
        ivan_history = ivan.receive_json()
        ivan_joined = ivan.receive_json()
        client.cookies.delete("session_id")

        expected_event = {
            "type": "game_ended",
            "game_id": game_id,
            "players": names,
            "ended_at": ended_at.timestamp(),
            "end_reason": "completed",
            "result": expected_event_result,
        }
        back_presence = {"type": "presence", "players": ["dave", "erin"], "count": 2}
        ivan_presence = {"type": "presence", "players": ["dave", "erin", "ivan"], "count": 3}
        assert [dave.receive_json() for _ in range(3)] == [
            back_presence,
            expected_event,
            ivan_presence,
        ]
        assert [events.receive_json() for _ in range(3)] == [back_presence, expected_event, ivan_presence]
        assert erin_joined["games"] == [{"game_id": game_id, "players": names, "started_at": ANY}]
        assert (ivan_joined["games"], ivan_joined["played"]) == (
            [],
            [
                {
                    "game_id": game_id,
                    "players": names,
                    "ended_at": ended_at.timestamp(),
                    "end_reason": "completed",
                    "result": expected_event_result,
                }
            ],
        )
        assert ivan_history == {"type": "history", "messages": []}

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


def test_events_socket__when_owner_rotates_its_key__should_close_with_credential_revoked(client, tournament_id):
    owner_key = issue_api_token(client)
    owner_session = client.cookies["session_id"]
    client.cookies.delete("session_id")
    del client.headers["origin"]

    with client.websocket_connect(
        f"/ws/tournaments/{tournament_id}/events", headers={"x-api-key": owner_key}
    ) as events:
        events.receive_json()

        client.cookies.set("session_id", owner_session)
        issue_api_token(client)
        with pytest.raises(WebSocketDisconnect) as closed:
            events.receive_json()

    assert closed.value.code == 4001


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
    owner_key = issue_api_token(client)
    tournament_game = TournamentGame(
        game_id="cup-game-1",
        tournament_id=tournament_id,
        players=["erin", "frank", "gina", "hank"],
        created_at=datetime(2026, 11, 11, 12, 0, tzinfo=UTC).timestamp(),
    )
    client.portal.call(app.state.tournament_repo.add_game, tournament_game)

    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice:
        _receive_until(ws_alice, "joined")

        deleted = post_lobby_json(client, f"/api/lobby/tournaments/{tournament_id}/delete")

        assert ws_alice.receive_json() == {"type": "error", "message": "tournament_deleted"}
        with pytest.raises(WebSocketDisconnect) as closed:
            ws_alice.receive_json()

    assert deleted.status_code == 200
    assert closed.value.code == 4000
    assert client.get(f"/api/lobby/tournaments/{tournament_id}").status_code == 404
    game_exit = client.get("/games/cup-game-1/exit", follow_redirects=False)
    assert (game_exit.status_code, game_exit.headers["location"]) == (303, "/")
    client.cookies.delete("session_id")
    assert client.get(f"/api/tournaments/{tournament_id}", headers={"x-api-key": owner_key}).status_code == 404


def test_tournament_finish__when_owner_finishes__should_close_sockets_and_keep_only_its_game_history(
    app, client, tournament_id
):
    owner_key = issue_api_token(client)
    repo = app.state.tournament_repo
    players = ["erin", "frank", "gina", "hank"]
    client.portal.call(
        repo.add_game,
        TournamentGame(game_id="cup-game-1", tournament_id=tournament_id, players=players, created_at=1.0),
    )
    client.portal.call(
        lambda: repo.finish_game("cup-game-1", ended_at=2.0, end_reason=GameEndReason.ABANDONED, result=[])
    )

    with (
        client.websocket_connect(f"/ws/tournaments/{tournament_id}") as ws_alice,
        client.websocket_connect(f"/ws/tournaments/{tournament_id}/events") as events,
    ):
        _receive_until(ws_alice, "joined")
        _receive_until(events, "presence")

        finished = post_lobby_json(client, f"/api/lobby/tournaments/{tournament_id}/finish")

        for socket in (ws_alice, events):
            assert _receive_until(socket, "error") == {"type": "error", "message": "tournament_finished"}
            with pytest.raises(WebSocketDisconnect) as closed:
                socket.receive_json()
            assert closed.value.code == 4000

    assert finished.status_code == 200
    finished_at = finished.json()["finished_at"]
    again = post_lobby_json(client, f"/api/lobby/tournaments/{tournament_id}/finish")
    assert (again.status_code, again.json()) == (409, {"error": "tournament_finished"})
    page = client.get(f"/api/lobby/tournaments/{tournament_id}").json()
    assert page["finished_at"] == finished_at
    assert page["played"] == [
        {"game_id": "cup-game-1", "players": players, "ended_at": 2.0, "end_reason": "abandoned", "result": []}
    ]
    [listed] = client.get("/api/lobby/tournaments").json()["own"]
    assert (listed["id"], listed["finished_at"]) == (tournament_id, finished_at)
    with client.websocket_connect(f"/ws/tournaments/{tournament_id}") as rejoined:
        assert rejoined.receive_json() == {"type": "error", "message": "tournament_finished"}
    client.cookies.delete("session_id")
    started = client.post(
        f"/api/tournaments/{tournament_id}/games", json={"games": [players]}, headers={"x-api-key": owner_key}
    )
    assert (started.status_code, started.json()) == (409, {"error": "tournament_finished"})


def test_tournament_delete__when_user_is_not_owner__should_return_404(client, tournament_id):
    login_with_csrf(client, "bob")

    refused = post_lobby_json(client, f"/api/lobby/tournaments/{tournament_id}/delete")

    assert (refused.status_code, refused.json()) == (404, {"error": "tournament_not_found"})
    assert client.get(f"/api/lobby/tournaments/{tournament_id}").status_code == 200


def test_tournament_create__when_non_admin_posts_name__should_list_it_and_open_its_pages(client):
    register_with_csrf(client, "organizer")

    tournament_id = create_tournament(client, "  Spring Cup  ")

    listed = client.get("/api/lobby/tournaments").json()
    assert [{key: value for key, value in entry.items() if key != "created_at"} for entry in listed["own"]] == [
        {"id": tournament_id, "name": "Spring Cup", "finished_at": None, "playing": 0, "finished": 0}
    ]
    assert (listed["others"], listed["can_create"], listed["name_max_length"]) == ([], True, 80)
    assert client.get("/tournaments").status_code == 200
    assert client.get(f"/tournaments/{tournament_id}").status_code == 200
    page = client.get(f"/api/lobby/tournaments/{tournament_id}").json()
    assert page == {
        "name": "Spring Cup",
        "finished_at": None,
        "played": None,
        "ws_url": f"ws://testserver/ws/tournaments/{tournament_id}",
        "chat_max_length": 1000,
        "name_max_length": 80,
        "is_owner": True,
    }


def test_tournament_create__when_guest_posts_name__should_refuse_with_403_and_list_no_create(client):
    client.get("/login")
    client.post("/api/lobby/auth/guest", json={}, headers={CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]})

    refused = post_lobby_json(client, "/api/lobby/tournaments", {"name": "Cup"})

    assert (refused.status_code, refused.json()) == (403, {"error": "guest_account"})
    listed = client.get("/api/lobby/tournaments").json()
    assert (listed["own"], listed["can_create"]) == ([], False)


def test_tournament_create__when_creation_is_closed__should_refuse_with_403_and_list_no_create(client, monkeypatch):
    monkeypatch.setattr(tournament_handlers, "TOURNAMENT_CREATION_CLOSED", True)
    register_with_csrf(client, "organizer")

    refused = post_lobby_json(client, "/api/lobby/tournaments", {"name": "Cup"})

    assert (refused.status_code, refused.json()) == (403, {"error": "tournament_creation_closed"})
    listed = client.get("/api/lobby/tournaments").json()
    assert (listed["own"], listed["can_create"]) == ([], False)


def test_tournament_page_route__when_other_user_opens_it__should_not_call_them_owner(client, tournament_id):
    login_with_csrf(client, "bob")

    page = client.get(f"/api/lobby/tournaments/{tournament_id}")
    listed = client.get("/api/lobby/tournaments").json()

    assert (page.status_code, page.json()["is_owner"]) == (200, False)
    assert (listed["own"], [entry["id"] for entry in listed["others"]]) == ([], [tournament_id])


def test_tournament_rename__when_owner_posts_new_name__should_store_the_stripped_name(client, tournament_id):
    renamed = post_lobby_json(client, f"/api/lobby/tournaments/{tournament_id}/rename", {"name": " Autumn Cup "})

    assert renamed.json() == {"name": "Autumn Cup"}
    assert client.get(f"/api/lobby/tournaments/{tournament_id}").json()["name"] == "Autumn Cup"


def test_tournament_create__when_name_has_format_character__should_refuse_and_create_nothing(client):
    register_with_csrf(client, "organizer")

    refused = post_lobby_json(client, "/api/lobby/tournaments", {"name": "Spring\u202eCup"})

    assert (refused.status_code, refused.json()) == (400, {"error": "invalid_name"})
    assert client.get("/api/lobby/tournaments").json()["own"] == []


def test_tournament_page_route__when_id_unknown__should_answer_404(client):
    register_with_csrf(client, "player")

    response = client.get("/api/lobby/tournaments/unknown-id")

    assert (response.status_code, response.json()) == (404, {"error": "tournament_not_found"})
