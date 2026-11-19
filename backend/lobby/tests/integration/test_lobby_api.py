import sqlite3
from contextlib import closing

import pytest

from lobby.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from lobby.tests.integration.conftest import grant_admin, register_with_csrf


def _revoke_admin(client, username: str) -> None:
    with closing(sqlite3.connect(client.app.state.auth_settings.database_path)) as conn, conn:
        conn.execute(
            "UPDATE players SET data = json_set(data, '$.is_admin', json('false')) WHERE username = ?", (username,)
        )


class TestLobbySessionRoute:
    def test_lobby_session_route__when_guest__should_report_a_guest_who_is_not_admin(self, client):
        client.get("/login")
        client.post("/guest", data={"csrf_token": client.cookies[CSRF_COOKIE_NAME]})

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
