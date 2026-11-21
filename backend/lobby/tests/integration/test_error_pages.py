import re

import pytest
from starlette.routing import Route
from starlette.testclient import TestClient

from app.auth.csrf import CSRF_COOKIE_NAME
from app.auth.policy import public_route
from tests.integration.conftest import register_with_csrf

_ERROR_META = ("status", "code", "action")
BROWSER_ACCEPT = {"accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


async def _crash(_request):
    raise RuntimeError("boom")


def _error_meta(page: str) -> tuple[str, ...]:
    found = [re.search(f'<meta name="ronin-error-{name}" content="([^"]*)">', page) for name in _ERROR_META]
    return tuple(match[1] if match else "" for match in found)


class TestErrorPages:
    def test_not_found__when_browser_navigates__should_render_the_error_page_for_the_lobby_app_to_word(self, client):
        register_with_csrf(client, "lostuser")

        response = client.get("/no-such-page", headers=BROWSER_ACCEPT)
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")
        assert _error_meta(response.text) == ("404", "not_found", "/")
        assert (
            '<section class="lobby-error-page" aria-labelledby="error-title" data-error-view></section>'
            in response.text
        )
        assert "data-lobby-nav" in response.text
        assert "Page not found" not in response.text

    def test_not_found__when_client_does_not_ask_for_html__should_keep_plain_text(self, client):
        response = client.get("/api/no-such-endpoint", headers={"accept": "*/*"})
        assert response.status_code == 404
        assert response.text == "Not Found"

    def test_http_error__when_request_is_refused__should_name_it_refused_without_the_detail(self, client):
        response = client.get("/logout", headers=BROWSER_ACCEPT)
        assert response.status_code == 405
        assert _error_meta(response.text) == ("405", "refused", "/")
        assert "Method Not Allowed" not in response.text

    def test_server_error__when_browser_navigates__should_render_the_error_page_with_security_headers(self, app):
        app.router.routes.append(Route("/crash", public_route(_crash), methods=["GET"]))

        with TestClient(app, raise_server_exceptions=False) as client:
            register_with_csrf(client, "crashuser")
            response = client.get("/crash", headers=BROWSER_ACCEPT)
        assert response.status_code == 500
        assert _error_meta(response.text) == ("500", "server", "/")
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["content-security-policy"].startswith("default-src 'self'")


class TestCsrfFailurePage:
    @pytest.mark.parametrize(
        ("referer", "action_href"),
        [
            ("http://testserver/history?page=2", "/history?page=2"),
            ("http://testserver//evil.example/x", "/evil.example/x"),
            ("http://testserver/\\evil.example/x", "/evil.example/x"),
            ("http://evil.example/", "/"),
            ("http://[", "/"),
        ],
        ids=["same_origin", "protocol_relative_path", "backslash_path", "other_origin", "malformed"],
    )
    def test_csrf_failure_page__when_form_is_stale__should_link_only_to_a_same_origin_page(
        self, client, referer, action_href
    ):
        register_with_csrf(client, "staleuser")

        response = client.post("/logout", data={"csrf_token": "stale"}, headers={"referer": referer})
        assert response.status_code == 403
        assert _error_meta(response.text) == ("403", "session_expired", action_href)
        assert "set-cookie" not in response.headers

    def test_csrf_failure_page__when_csrf_cookie_is_missing__should_set_one_its_meta_token_carries(self, client):
        register_with_csrf(client, "cookielessuser")
        client.cookies.delete(CSRF_COOKIE_NAME)

        response = client.post("/logout", data={"csrf_token": "stale"})
        fresh_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert response.status_code == 403
        assert fresh_token is not None
        assert f'<meta name="csrf-token" content="{fresh_token}">' in response.text

        logout = client.post("/logout", data={"csrf_token": fresh_token}, follow_redirects=False)
        assert (logout.status_code, logout.headers["location"]) == (303, "/login")

    @pytest.mark.parametrize(
        ("path", "status_code"), [("/logout", 403), ("/no-such-page", 404)], ids=["stale_logout_form", "not_found_page"]
    )
    def test_page_render__when_post_comes_from_another_site__should_not_replace_the_withheld_csrf_cookie(
        self, client, path, status_code
    ):
        client.get("/login")
        client.cookies.delete(CSRF_COOKIE_NAME)

        response = client.post(
            path,
            data={"csrf_token": "attacker"},
            headers={**BROWSER_ACCEPT, "sec-fetch-site": "cross-site"},
        )
        assert response.status_code == status_code
        assert "set-cookie" not in response.headers
