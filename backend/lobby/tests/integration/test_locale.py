import pytest

from app.auth.csrf import CSRF_COOKIE_NAME


def test_page_locale__when_resolved_from_accept_language__should_vary_on_it_and_the_cookie(client):
    from_header = client.get("/login", headers={"accept-language": "ru-RU,ru;q=0.9"})
    client.cookies.set("lang", "ja")
    from_cookie = client.get("/login", headers={"accept-language": "ru-RU,ru;q=0.9"})
    assert '<html lang="ru"' in from_header.text
    assert {"Accept-Language", "Cookie"} <= set(from_header.headers["vary"].split(", "))
    assert '<html lang="ja"' in from_cookie.text
    assert "Cookie" in from_cookie.headers["vary"].split(", ")
    assert "Accept-Language" not in from_cookie.headers["vary"]


def test_legal_page__when_lang_cookie_is_ja__should_render_a_japanese_page_with_the_chrome_mounts_and_meta(client):
    client.cookies.set("lang", "ja")

    response = client.get("/terms")
    assert '<html lang="ja"' in response.text
    assert '<nav class="container lobby-nav" data-lobby-nav></nav>' in response.text
    assert '<footer class="container" data-lobby-footer></footer>' in response.text
    assert '<main class="container"><div class="lobby-alert warning" data-browser-notice hidden></div>' in response.text
    assert f'<meta name="csrf-token" content="{client.cookies[CSRF_COOKIE_NAME]}">' in response.text
    assert '<meta name="ronin-app-version" content="dev">' in response.text
    assert "<title>利用規約 · Ronin Beta</title>" in response.text
    assert "lobby-nav-link" not in response.text
    assert 'action="/lang"' not in response.text


@pytest.mark.parametrize(
    ("path", "lang", "heading"),
    [
        ("/terms", "ja", "<h1>利用規約</h1>"),
        ("/privacy", "ru", "<h1>Политика конфиденциальности</h1>"),
        ("/terms", None, "<h1>Terms of Service</h1>"),
    ],
    ids=["terms_ja", "privacy_ru", "terms_default_en"],
)
def test_legal_page__when_visitor_is_anonymous__should_render_the_document_written_in_the_page_language(
    client, path, lang, heading
):
    if lang is not None:
        client.cookies.set("lang", lang)

    response = client.get(path, follow_redirects=False)
    assert response.status_code == 200
    assert f'<html lang="{lang or "en"}"' in response.text
    assert response.text.count(heading) == 1
