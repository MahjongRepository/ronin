from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from starlette.datastructures import FormData
from starlette.requests import Request

from lobby.auth.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FORM_FIELD,
    get_or_create_csrf_token,
    is_cross_site_post,
    is_csrf_valid,
    set_csrf_cookie,
)


def _make_request(cookies: dict[str, str] | None = None) -> MagicMock:
    request = MagicMock()
    request.cookies = cookies or {}
    return request


class TestGetOrCreateCsrfToken:
    def test_get_or_create_csrf_token__when_cookie_present__should_return_existing_token(self):
        request = _make_request({CSRF_COOKIE_NAME: "existing-token"})

        token, is_new = get_or_create_csrf_token(request)
        assert token == "existing-token"
        assert is_new is False

    def test_get_or_create_csrf_token__when_no_cookie__should_generate_new_token(self):
        request = _make_request()

        token, is_new = get_or_create_csrf_token(request)
        assert len(token) == 43
        assert is_new is True

    def test_get_or_create_csrf_token__when_called_twice_without_cookie__should_generate_unique_tokens(self):
        request = _make_request()

        token1, _ = get_or_create_csrf_token(request)
        token2, _ = get_or_create_csrf_token(request)
        assert token1 != token2


class TestSetCsrfCookie:
    def test_set_csrf_cookie__when_secure__should_set_secure_flag(self):
        response = MagicMock()
        set_csrf_cookie(response, token="test-token", cookie_secure=True)
        response.set_cookie.assert_called_once_with(
            key=CSRF_COOKIE_NAME,
            value="test-token",
            httponly=True,
            samesite="lax",
            secure=True,
            path="/",
        )

    def test_set_csrf_cookie__when_not_secure__should_omit_secure_flag(self):
        response = MagicMock()
        set_csrf_cookie(response, token="test-token", cookie_secure=False)
        response.set_cookie.assert_called_once_with(
            key=CSRF_COOKIE_NAME,
            value="test-token",
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )


class TestIsCsrfValid:
    def test_is_csrf_valid__when_cookie_missing__should_reject(self):
        request = _make_request()
        form = FormData({CSRF_FORM_FIELD: "some-token"})

        assert is_csrf_valid(request, form) is False

    def test_is_csrf_valid__when_form_field_missing__should_reject(self):
        request = _make_request({CSRF_COOKIE_NAME: "token-value"})
        form = FormData({})

        assert is_csrf_valid(request, form) is False

    @pytest.mark.parametrize("form_token", ["token-b", "tökén-ä"], ids=["ascii", "non_ascii"])
    def test_is_csrf_valid__when_tokens_mismatch__should_reject(self, form_token: str):
        request = _make_request({CSRF_COOKIE_NAME: "token-a"})
        form = FormData({CSRF_FORM_FIELD: form_token})

        assert is_csrf_valid(request, form) is False

    def test_is_csrf_valid__when_tokens_match__should_accept(self):
        request = _make_request({CSRF_COOKIE_NAME: "matching-token"})
        form = FormData({CSRF_FORM_FIELD: "matching-token"})

        assert is_csrf_valid(request, form) is True

    def test_is_csrf_valid__when_cookie_empty__should_reject(self):
        request = _make_request({CSRF_COOKIE_NAME: ""})
        form = FormData({CSRF_FORM_FIELD: ""})

        assert is_csrf_valid(request, form) is False


def _make_http_request(method: str, headers: dict[str, str]) -> Request:
    raw_headers = [(b"host", b"lobby.example")] + [(name.encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "method": method, "scheme": "https", "path": "/login", "headers": raw_headers})


class TestIsCrossSitePost:
    @pytest.mark.parametrize(
        ("method", "headers", "expected"),
        [
            ("GET", {"sec-fetch-site": "cross-site"}, False),
            ("POST", {"sec-fetch-site": "cross-site", "origin": "https://lobby.example"}, True),
            ("POST", {"sec-fetch-site": "same-site", "origin": "https://evil.example"}, False),
            ("POST", {"origin": "https://evil.example"}, True),
            ("POST", {"origin": "null"}, True),
            ("POST", {"origin": "http://["}, True),
            ("POST", {"origin": "https://lobby.example"}, False),
            ("POST", {"origin": "http://lobby.example"}, True),
            ("POST", {}, False),
        ],
        ids=[
            "get_carries_lax_cookies",
            "fetch_site_wins_over_origin",
            "same_site_carries_lax_cookies",
            "foreign_origin",
            "null_origin",
            "malformed_origin",
            "own_origin",
            "own_host_other_scheme",
            "no_hint",
        ],
    )
    def test_is_cross_site_post__when_request_hints_its_site__should_judge_fetch_site_before_origin(
        self, method, headers, expected
    ):
        assert is_cross_site_post(_make_http_request(method, headers)) is expected
