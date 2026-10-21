from __future__ import annotations

from typing import TYPE_CHECKING

from lobby.server.csrf import CSRF_COOKIE_NAME

if TYPE_CHECKING:
    from starlette.testclient import TestClient


def register_with_csrf(client: TestClient, username: str) -> None:
    response = client.get("/register")
    csrf = response.cookies.get(CSRF_COOKIE_NAME) or client.cookies.get(CSRF_COOKIE_NAME)
    client.post(
        "/register",
        data={
            "username": username,
            "password": "securepass123",
            "confirm_password": "securepass123",
            "csrf_token": csrf,
        },
    )


def login_with_csrf(client: TestClient, username: str) -> None:
    response = client.get("/login")
    csrf = response.cookies.get(CSRF_COOKIE_NAME) or client.cookies.get(CSRF_COOKIE_NAME)
    client.post(
        "/login",
        data={"username": username, "password": "securepass123", "csrf_token": csrf},
    )


def logout_with_csrf(client: TestClient) -> None:
    response = client.get("/")
    csrf = response.cookies.get(CSRF_COOKIE_NAME) or client.cookies.get(CSRF_COOKIE_NAME)
    client.post("/logout", data={"csrf_token": csrf})
