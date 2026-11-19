from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

from lobby.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

if TYPE_CHECKING:
    import httpx2
    from starlette.testclient import TestClient


def _csrf_headers(client: TestClient) -> dict[str, str]:
    client.get("/login")
    return {CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]}


def register_with_csrf(client: TestClient, username: str) -> None:
    client.post(
        "/api/lobby/auth/register",
        json={"username": username, "password": "securepass123", "confirm_password": "securepass123"},
        headers=_csrf_headers(client),
    )


def login_with_csrf(client: TestClient, username: str) -> None:
    client.post(
        "/api/lobby/auth/login",
        json={"username": username, "password": "securepass123"},
        headers=_csrf_headers(client),
    )


def logout_with_csrf(client: TestClient) -> None:
    response = client.get("/")
    csrf = response.cookies.get(CSRF_COOKIE_NAME) or client.cookies.get(CSRF_COOKIE_NAME)
    client.post("/logout", data={"csrf_token": csrf})


def grant_admin(client: TestClient, username: str) -> None:
    with closing(sqlite3.connect(client.app.state.auth_settings.database_path)) as conn, conn:
        conn.execute(
            "UPDATE players SET data = json_set(data, '$.is_admin', json('true')) WHERE username = ?", (username,)
        )


def post_lobby_json(client: TestClient, path: str, body: dict | None = None) -> httpx2.Response:
    return client.post(path, json=body if body is not None else {}, headers=_csrf_headers(client))


def issue_api_token(client: TestClient) -> str:
    issued = post_lobby_json(client, "/api/lobby/api-token")
    assert issued.status_code == 201, issued.text
    return issued.json()["token"]


def create_tournament(client: TestClient, name: str = "Cup") -> str:
    created = post_lobby_json(client, "/api/lobby/tournaments", {"name": name})
    assert created.status_code == 201, created.text
    return created.json()["tournament_id"]


def session_user_id(client: TestClient) -> str:
    token_hash = hashlib.sha256(client.cookies["session_id"].encode()).hexdigest()
    with closing(sqlite3.connect(client.app.state.auth_settings.database_path)) as conn:
        (user_id,) = conn.execute("SELECT user_id FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
    return user_id
