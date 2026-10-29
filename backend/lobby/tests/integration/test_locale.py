import pytest
from starlette.testclient import TestClient

from lobby.auth.csrf import CSRF_COOKIE_NAME
from lobby.tests.integration.conftest import register_with_csrf

BROWSER_ACCEPT = {"accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


def _csrf_token(client) -> str:
    client.get("/login")
    token = client.cookies.get(CSRF_COOKIE_NAME)
    assert token, "GET /login set no CSRF cookie"
    return token


def _lang_set_cookie(response) -> str | None:
    headers = [value for value in response.headers.get_list("set-cookie") if value.startswith("lang=")]
    assert len(headers) <= 1
    return headers[0] if headers else None


class TestSetLanguageRoute:
    @pytest.mark.parametrize(
        ("next_path", "location"),
        [
            ("/login?next=%2Fhistory", "/login?next=%2Fhistory"),
            ("//evil.example/x", "/"),
            ("https://evil.example/", "/"),
            (None, "/"),
        ],
        ids=["safe_path", "protocol_relative", "absolute_url", "absent"],
    )
    def test_set_language_route__when_lang_is_supported__should_set_the_cookie_and_return_to_a_safe_page(
        self, client, next_path, location
    ):
        form = {"csrf_token": _csrf_token(client), "lang": "ja"}
        if next_path is not None:
            form["next"] = next_path

        response = client.post("/lang", data=form, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == location
        cookie = _lang_set_cookie(response)
        assert cookie is not None
        attributes = {part.strip().split("=")[0].lower() for part in cookie.split(";")}
        assert cookie.startswith("lang=ja;")
        assert "Max-Age=31536000" in cookie
        assert "Path=/" in cookie
        assert "SameSite=lax" in cookie
        assert "httponly" not in attributes
        assert "secure" not in attributes

    def test_set_language_route__when_cookies_are_secure__should_mark_the_cookie_secure(self, make_app, monkeypatch):
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")

        with TestClient(make_app(), base_url="https://testserver") as client:
            client.get("/login")
            token = client.cookies.get(CSRF_COOKIE_NAME)
            response = client.post("/lang", data={"csrf_token": token, "lang": "ru"}, follow_redirects=False)
        cookie = _lang_set_cookie(response)
        assert cookie is not None
        assert "secure" in {part.strip().lower() for part in cookie.split(";")}

    def test_set_language_route__when_csrf_token_is_stale__should_render_the_session_expired_page_without_a_cookie(
        self, client
    ):
        _csrf_token(client)

        response = client.post("/lang", data={"csrf_token": "stale", "lang": "ja"}, follow_redirects=False)
        assert response.status_code == 403
        assert "Session expired" in response.text
        assert _lang_set_cookie(response) is None

    def test_set_language_route__when_lang_is_unsupported__should_answer_400_without_a_cookie(self, client):
        response = client.post("/lang", data={"csrf_token": _csrf_token(client), "lang": "de"}, headers=BROWSER_ACCEPT)
        assert response.status_code == 400
        assert _lang_set_cookie(response) is None


def test_page_locale__when_resolved_from_accept_language__should_vary_on_it_and_the_cookie(client):
    from_header = client.get("/login", headers={"accept-language": "ru-RU,ru;q=0.9"})
    client.cookies.set("lang", "ja")
    from_cookie = client.get("/login", headers={"accept-language": "ru-RU,ru;q=0.9"})
    assert '<html lang="ru"' in from_header.text
    assert {"Accept-Language", "Cookie"} <= set(from_header.headers["vary"].split(", "))
    assert '<html lang="ja"' in from_cookie.text
    assert "Cookie" in from_cookie.headers["vary"].split(", ")
    assert "Accept-Language" not in from_cookie.headers["vary"]


def test_login_page__when_lang_cookie_is_ja__should_render_in_japanese(client):
    client.cookies.set("lang", "ja")

    response = client.get("/login")
    assert '<html lang="ja"' in response.text
    assert "<h1>ログイン</h1>" in response.text


def test_register_route__when_username_taken_and_lang_is_ru__should_show_the_russian_error_with_the_name(client):
    register_with_csrf(client, "taken_name")
    client.cookies.delete("session_id")
    client.cookies.set("lang", "ru")

    response = client.post(
        "/register",
        data={
            "username": "taken_name",
            "password": "securepass123",
            "confirm_password": "securepass123",
            "csrf_token": client.cookies.get(CSRF_COOKIE_NAME),
        },
    )
    assert '<html lang="ru"' in response.text
    assert "Имя «taken_name» уже занято." in response.text


def test_language_switch__when_page_is_rendered__should_mark_the_active_language_and_return_to_the_page(client):
    client.cookies.set("lang", "ru")

    response = client.get("/login?next=%2Fhistory")
    footer = response.text.split("<footer", 1)[1]
    assert 'action="/lang"' in footer
    assert 'action="/lang"' not in response.text.split("<footer", 1)[0]
    assert '<input type="hidden" name="next" value="/login?next=%2Fhistory">' in response.text
    assert 'value="ru" lang="ru" aria-current="true">Русский</button>' in response.text
    assert 'value="ja" lang="ja">日本語</button>' in response.text
    assert 'value="en" lang="en">English</button>' in response.text


@pytest.mark.parametrize(
    ("referer", "return_page"),
    [("http://testserver/history?page=2", "/history?page=2"), (None, "/")],
    ids=["same_origin_referer", "no_referer"],
)
def test_language_switch__when_page_answers_a_post__should_return_to_the_posting_page_instead_of_the_post_target(
    client, referer, return_page
):
    _csrf_token(client)
    headers = {"referer": referer} if referer else {}

    response = client.post("/lang", data={"csrf_token": "stale", "lang": "ja"}, headers=headers)
    assert response.status_code == 403
    assert f'<input type="hidden" name="next" value="{return_page}">' in response.text
    assert 'name="next" value="/lang"' not in response.text
