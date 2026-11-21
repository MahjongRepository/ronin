import pytest

from app.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.auth.service import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from app.rate_limit import KeyedRateLimiter
from app.views.auth_handlers import GUEST_LOGIN_REFILL_PER_SECOND
from tests.integration.conftest import register_with_csrf

_CREDENTIALS = {"username": "newuser", "password": "securepass123", "confirm_password": "securepass123"}


def _csrf_headers(client) -> dict[str, str]:
    client.get("/login")
    return {CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]}


@pytest.mark.parametrize("endpoint", ["login", "register", "guest"])
def test_auth_api__when_csrf_header_stale__should_answer_csrf_invalid_without_a_session_or_spending_the_guest_budget(
    client, endpoint
):
    register_with_csrf(client, "newuser")
    client.cookies.delete("session_id")
    client.app.state.guest_login_limiter = KeyedRateLimiter(rate=GUEST_LOGIN_REFILL_PER_SECOND, burst=1)

    rejected = client.post(f"/api/lobby/auth/{endpoint}", json=_CREDENTIALS, headers={CSRF_HEADER_NAME: "stale-token"})
    guest = client.post("/api/lobby/auth/guest", json={}, headers=_csrf_headers(client))

    assert rejected.status_code == 403
    assert rejected.json()["error"] == "csrf_invalid"
    assert "session_id" not in rejected.cookies
    assert guest.status_code == 200


class TestLoginApi:
    def test_login_api__when_password_wrong__should_answer_wrong_credentials(self, client):
        register_with_csrf(client, "newuser")
        client.cookies.delete("session_id")

        response = client.post(
            "/api/lobby/auth/login",
            json={"username": "newuser", "password": "wrong-password"},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 400
        assert response.json() == {"error": "auth_error", "code": "wrong_credentials", "params": {}, "field": None}
        assert "session_id" not in response.cookies

    def test_login_api__when_next_is_a_local_path__should_return_it_with_a_session(self, client):
        register_with_csrf(client, "newuser")
        client.cookies.delete("session_id")

        response = client.post(
            "/api/lobby/auth/login",
            json={"username": "newuser", "password": "securepass123", "next": "/rooms/r1?tab=chat"},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 200
        assert response.json() == {"next": "/rooms/r1?tab=chat"}
        assert "session_id" in response.cookies


class TestRegisterApi:
    def test_register_api__when_password_too_short__should_answer_the_auth_error_code_with_its_params(self, client):
        response = client.post(
            "/api/lobby/auth/register",
            json={"username": "newuser", "password": "short", "confirm_password": "short"},
            headers=_csrf_headers(client),
        )

        assert response.status_code == 400
        assert response.json() == {
            "error": "auth_error",
            "code": "password_length",
            "params": {"min": PASSWORD_MIN_LENGTH, "max": PASSWORD_MAX_LENGTH},
            "field": "password",
        }
        assert "session_id" not in response.cookies

    def test_register_api__when_next_leaves_the_site__should_start_a_session_and_return_the_lobby(self, client):
        response = client.post(
            "/api/lobby/auth/register",
            json={
                "username": "newuser",
                "password": "securepass123",
                "confirm_password": "securepass123",
                "next": "//evil.example",
            },
            headers=_csrf_headers(client),
        )

        assert response.status_code == 200
        assert response.json() == {"next": "/"}
        assert response.headers["cache-control"] == "no-store"
        assert "session_id" in response.cookies
        assert client.get("/api/lobby/session").json()["user"]["username"] == "newuser"
