from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

from lobby.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

if TYPE_CHECKING:
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


def session_user_id(client: TestClient) -> str:
    token_hash = hashlib.sha256(client.cookies["session_id"].encode()).hexdigest()
    with closing(sqlite3.connect(client.app.state.auth_settings.database_path)) as conn:
        (user_id,) = conn.execute("SELECT user_id FROM sessions WHERE token_hash = ?", (token_hash,)).fetchone()
    return user_id
