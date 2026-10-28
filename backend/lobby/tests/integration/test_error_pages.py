import pytest
from starlette.routing import Route
from starlette.testclient import TestClient

from lobby.auth.csrf import CSRF_COOKIE_NAME
from lobby.auth.policy import public_route
from lobby.tests.integration.conftest import register_with_csrf

BROWSER_ACCEPT = {"accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


async def _crash(_request):
    raise RuntimeError("boom")


class TestErrorPages:
    def test_not_found__when_browser_navigates__should_render_the_lobby_error_page(self, client):
        register_with_csrf(client, "lostuser")

        response = client.get("/no-such-page", headers=BROWSER_ACCEPT)
        assert response.status_code == 404
        assert response.headers["content-type"].startswith("text/html")
        assert "Page not found" in response.text
        assert 'href="/" role="button"' in response.text
        assert "lostuser" in response.text

    def test_not_found__when_client_does_not_ask_for_html__should_keep_plain_text(self, client):
        response = client.get("/api/no-such-endpoint", headers={"accept": "*/*"})
        assert response.status_code == 404
        assert response.text == "Not Found"

    def test_http_error__when_request_is_refused__should_not_ask_to_try_again(self, client):
        response = client.get("/logout", headers=BROWSER_ACCEPT)
        assert response.status_code == 405
        assert "Request refused" in response.text
        assert "Method Not Allowed" not in response.text
        assert "The server could not accept this request." in response.text
        assert "Try again" not in response.text

    def test_server_error__when_browser_navigates__should_render_the_lobby_error_page(self, app):
        app.router.routes.append(Route("/crash", public_route(_crash), methods=["GET"]))

        with TestClient(app, raise_server_exceptions=False) as client:
            register_with_csrf(client, "crashuser")
            response = client.get("/crash", headers=BROWSER_ACCEPT)
        assert response.status_code == 500
        assert "Something went wrong" in response.text
        assert "crashuser" in response.text
        assert 'action="/logout"' in response.text
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["content-security-policy"].startswith("default-src 'self'")


class TestCsrfFailurePage:
    @pytest.mark.parametrize(
        ("referer", "expected_link"),
        [
            ("http://testserver/history?page=2", 'href="/history?page=2" role="button">Reload the page'),
            ("http://testserver//evil.example/x", 'href="/evil.example/x" role="button">Reload the page'),
            ("http://testserver/\\evil.example/x", 'href="/evil.example/x" role="button">Reload the page'),
            ("http://evil.example/", 'href="/" role="button">Back to lobby'),
            ("http://[", 'href="/" role="button">Back to lobby'),
        ],
        ids=["same_origin", "protocol_relative_path", "backslash_path", "other_origin", "malformed"],
    )
    def test_csrf_failure_page__when_form_is_stale__should_link_only_to_a_same_origin_page(
        self, client, referer, expected_link
    ):
        register_with_csrf(client, "staleuser")

        response = client.post("/rooms/new", data={"csrf_token": "stale"}, headers={"referer": referer})
        assert response.status_code == 403
        assert "Session expired" in response.text
        assert expected_link in response.text
        assert "set-cookie" not in response.headers

    def test_csrf_failure_page__when_csrf_cookie_is_missing__should_set_one_its_log_out_form_carries(self, client):
        register_with_csrf(client, "cookielessuser")
        client.cookies.delete(CSRF_COOKIE_NAME)

        response = client.post("/rooms/new", data={"csrf_token": "stale"})
        fresh_token = client.cookies.get(CSRF_COOKIE_NAME)
        assert response.status_code == 403
        assert fresh_token is not None
        assert f'name="csrf_token" value="{fresh_token}"' in response.text

        logout = client.post("/logout", data={"csrf_token": fresh_token}, follow_redirects=False)
        assert (logout.status_code, logout.headers["location"]) == (303, "/login")

    @pytest.mark.parametrize(
        ("path", "status_code"), [("/login", 403), ("/no-such-page", 404)], ids=["stale_login_form", "not_found_page"]
    )
    def test_page_render__when_post_comes_from_another_site__should_not_replace_the_withheld_csrf_cookie(
        self, client, path, status_code
    ):
        client.get("/login")
        client.cookies.delete(CSRF_COOKIE_NAME)

        response = client.post(
            path,
            data={"username": "victim", "password": "x", "csrf_token": "attacker"},
            headers={**BROWSER_ACCEPT, "sec-fetch-site": "cross-site"},
        )
        assert response.status_code == status_code
        assert "set-cookie" not in response.headers
