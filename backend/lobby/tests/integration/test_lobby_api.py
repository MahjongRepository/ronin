import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from lobby.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from lobby.dal.models import GameEndReason, PlayedGame, PlayedGameStanding
from lobby.tests.integration.conftest import grant_admin, register_with_csrf, session_user_id
from lobby.views.history_handlers import HISTORY_GAMES_LIMIT


def _revoke_admin(client, username: str) -> None:
    with closing(sqlite3.connect(client.app.state.auth_settings.database_path)) as conn, conn:
        conn.execute(
            "UPDATE players SET data = json_set(data, '$.is_admin', json('false')) WHERE username = ?", (username,)
        )


class TestLobbySessionRoute:
    def test_lobby_session_route__when_guest__should_report_a_guest_who_is_not_admin(self, client):
        client.get("/login")
        client.post("/api/lobby/auth/guest", json={}, headers={CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]})

        response = client.get("/api/lobby/session")

        assert response.headers["cache-control"] == "no-store"
        payload = response.json()
        assert payload["user"]["username"].startswith("Nanashi-")
        assert payload["user"]["is_guest"] is True
        assert payload["user"]["is_admin"] is False
        assert payload["limits"] == {
            "username_min_length": 3,
            "username_max_length": 16,
            "password_min_length": 8,
            "password_max_length": 72,
        }

    def test_lobby_session_route__when_admin_flag_revoked__should_report_not_admin_at_the_next_request(self, client):
        register_with_csrf(client, "opsuser")
        grant_admin(client, "opsuser")

        granted = client.get("/api/lobby/session").json()["user"]
        _revoke_admin(client, "opsuser")
        revoked = client.get("/api/lobby/session").json()["user"]

        assert granted == {"username": "opsuser", "is_guest": False, "is_admin": True}
        assert revoked["is_admin"] is False


class TestLobbyRoomsRoute:
    def test_lobby_rooms_route__when_user_is_seated__should_name_their_room(self, client):
        register_with_csrf(client, "alice")
        room = client.app.state.room_manager.create_room("my-room-id")
        with client.websocket_connect("/ws/rooms/my-room-id") as ws:
            ws.receive_json()
            response = client.get("/api/lobby/rooms")

        payload = response.json()
        assert payload["my_room"] == "my-room-id"
        assert [listed["name"] for listed in payload["rooms"]] == [room.name]
        assert payload["games_ws_url"] == "ws://testserver/ws/games"

    def test_lobby_create_room_route__when_csrf_header_stale__should_answer_a_token_that_succeeds_on_retry(
        self, client
    ):
        register_with_csrf(client, "alice")

        rejected = client.post("/api/lobby/rooms", json={}, headers={CSRF_HEADER_NAME: "stale-token"})
        retried = client.post("/api/lobby/rooms", json={}, headers={CSRF_HEADER_NAME: rejected.json()["csrf_token"]})

        assert rejected.status_code == 403
        assert rejected.json()["error"] == "csrf_invalid"
        assert rejected.headers["cache-control"] == "no-store"
        assert retried.status_code == 201
        assert [room["room_id"] for room in client.app.state.room_manager.get_rooms_info()] == [
            retried.json()["room_id"]
        ]

    @pytest.mark.parametrize(
        ("fetch_site", "sets_cookie"), [("same-origin", True), ("cross-site", False)], ids=["same_origin", "cross_site"]
    )
    def test_lobby_create_room_route__when_csrf_cookie_gone__should_set_a_new_one_only_for_a_same_origin_post(
        self, client, fetch_site, sets_cookie
    ):
        register_with_csrf(client, "alice")
        client.cookies.delete(CSRF_COOKIE_NAME)

        rejected = client.post(
            "/api/lobby/rooms", json={}, headers={CSRF_HEADER_NAME: "stale-token", "sec-fetch-site": fetch_site}
        )

        assert rejected.status_code == 403
        assert rejected.json()["error"] == "csrf_invalid"
        new_cookie = rejected.cookies.get(CSRF_COOKIE_NAME)
        if not sets_cookie:
            assert new_cookie is None
            return

        assert new_cookie == rejected.json()["csrf_token"]
        retried = client.post(
            "/api/lobby/rooms", json={}, headers={CSRF_HEADER_NAME: new_cookie, "sec-fetch-site": fetch_site}
        )
        assert retried.status_code == 201


class TestLobbyRoomRoute:
    def test_lobby_room_route__when_room_exists__should_answer_its_name_socket_and_chat_limit_uncached(self, client):
        register_with_csrf(client, "alice")
        room = client.app.state.room_manager.create_room("room-42")

        response = client.get("/api/lobby/rooms/room-42")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "room_name": room.name,
            "ws_url": "ws://testserver/ws/rooms/room-42",
            "chat_max_length": 1000,
        }

    @pytest.mark.parametrize(
        ("game_session_status", "game_url"),
        [(200, "/play/game%201"), (404, None), (500, None)],
        ids=["playing", "not_playing", "lookup_failed"],
    )
    def test_lobby_room_route__when_room_not_found__should_answer_404_with_the_users_live_game_page(
        self, client, game_server, game_session_status, game_url
    ):
        register_with_csrf(client, "alice")
        game_server.respond = lambda _request: httpx.Response(
            game_session_status, json={"game_id": "game 1", "game_ticket": "ticket"}
        )

        response = client.get("/api/lobby/rooms/gone-room")

        assert response.status_code == 404
        assert response.json() == {"error": "room_not_found", "game_url": game_url}


class TestLobbyHistoryRoute:
    def test_lobby_history_route__when_another_user_held_the_viewers_name__should_mark_only_the_viewers_standing(
        self, client
    ):
        register_with_csrf(client, "gamesuser")
        viewer_id = session_user_id(client)
        started_at = datetime(2026, 10, 24, 3, 9, tzinfo=UTC)
        client.app.state.game_repo.create_game(
            PlayedGame(
                game_id="name-reuse-game",
                started_at=started_at,
                ended_at=started_at + timedelta(minutes=45),
                end_reason=GameEndReason.COMPLETED,
                game_type="hanchan",
                num_rounds_played=8,
                standings=[
                    PlayedGameStanding(name="gamesuser", seat=0, user_id="earlier-holder", score=41000, final_score=51),
                    PlayedGameStanding(name="gamesuser", seat=2, user_id=viewer_id, score=27000, final_score=7),
                    PlayedGameStanding(name="Tsumogiri 1", seat=1, score=19000, final_score=-21),
                    PlayedGameStanding(name="Tsumogiri 2", seat=3, score=13000, final_score=-37),
                ],
            ),
        )

        response = client.get("/api/lobby/history")

        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "games": [
                {
                    "game_id": "name-reuse-game",
                    "started_at": "2026-10-24T03:09:00+00:00",
                    "num_rounds_played": 8,
                    "duration_seconds": 2700.0,
                    "game_type": "hanchan",
                    "wind": "南",
                    "players": [
                        {"name": "gamesuser", "score": 41000, "final_score": 51, "is_winner": True, "is_viewer": False},
                        {"name": "gamesuser", "score": 27000, "final_score": 7, "is_winner": False, "is_viewer": True},
                        {
                            "name": "Tsumogiri 1",
                            "score": 19000,
                            "final_score": -21,
                            "is_winner": False,
                            "is_viewer": False,
                        },
                        {
                            "name": "Tsumogiri 2",
                            "score": 13000,
                            "final_score": -37,
                            "is_winner": False,
                            "is_viewer": False,
                        },
                    ],
                    "replay_url": "/play/history/name-reuse-game",
                    "viewer_replay_url": "/play/history/name-reuse-game?seat=2",
                }
            ]
        }

    def test_lobby_history_route__when_more_games_than_the_limit__should_answer_the_most_recent_newest_first(
        self, client
    ):
        register_with_csrf(client, "gamesuser")
        now = datetime.now(UTC)
        game_ids = [f"ordered-game-{index:02}" for index in range(HISTORY_GAMES_LIMIT + 1)]
        for index, game_id in enumerate(game_ids):
            client.app.state.game_repo.create_game(
                PlayedGame(
                    game_id=game_id,
                    started_at=now - timedelta(hours=len(game_ids) - index),
                    end_reason=GameEndReason.COMPLETED,
                    game_type="hanchan",
                ),
            )

        response = client.get("/api/lobby/history")

        assert [game["game_id"] for game in response.json()["games"]] == game_ids[:0:-1]


class TestLobbyMatchmakingRoute:
    def test_lobby_matchmaking_route__when_signed_in__should_answer_the_queue_socket_uncached(self, client):
        register_with_csrf(client, "alice")

        response = client.get("/api/lobby/matchmaking")

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"ws_url": "ws://testserver/ws/matchmaking"}
