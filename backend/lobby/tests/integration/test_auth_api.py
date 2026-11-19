from lobby.auth.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from shared.auth.service import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


def _csrf_headers(client) -> dict[str, str]:
    client.get("/login")
    return {CSRF_HEADER_NAME: client.cookies[CSRF_COOKIE_NAME]}


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
