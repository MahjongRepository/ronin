"""Shared test helpers for lobby integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lobby.server.csrf import CSRF_COOKIE_NAME

if TYPE_CHECKING:
    from starlette.testclient import TestClient


def register_with_csrf(client: TestClient, username: str) -> None:
    """Register a user via GET (to obtain CSRF token) + POST."""
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
    """Log in a user via GET (to obtain CSRF token) + POST."""
    response = client.get("/login")
    csrf = response.cookies.get(CSRF_COOKIE_NAME) or client.cookies.get(CSRF_COOKIE_NAME)
    client.post(
        "/login",
        data={"username": username, "password": "securepass123", "csrf_token": csrf},
    )


def logout_with_csrf(client: TestClient) -> None:
    """Log out a user via GET (to obtain CSRF token) + POST."""
    response = client.get("/")
    csrf = response.cookies.get(CSRF_COOKIE_NAME) or client.cookies.get(CSRF_COOKIE_NAME)
    client.post("/logout", data={"csrf_token": csrf})
