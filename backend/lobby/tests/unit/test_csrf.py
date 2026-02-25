"""Tests for CSRF protection helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from starlette.datastructures import FormData

from lobby.server.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FORM_FIELD,
    get_or_create_csrf_token,
    set_csrf_cookie,
    validate_csrf,
)


def _make_request(cookies: dict[str, str] | None = None) -> MagicMock:
    request = MagicMock()
    request.cookies = cookies or {}
    return request


class TestGetOrCreateCsrfToken:
    def test_returns_existing_token_from_cookie(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: "existing-token"})
        token, is_new = get_or_create_csrf_token(request)
        assert token == "existing-token"
        assert is_new is False

    def test_generates_new_token_when_no_cookie(self) -> None:
        request = _make_request()
        token, is_new = get_or_create_csrf_token(request)
        assert len(token) > 0
        assert is_new is True

    def test_generated_tokens_are_unique(self) -> None:
        request = _make_request()
        token1, _ = get_or_create_csrf_token(request)
        token2, _ = get_or_create_csrf_token(request)
        assert token1 != token2


class TestSetCsrfCookie:
    def test_sets_cookie_with_secure_flag(self) -> None:
        response = MagicMock()
        set_csrf_cookie(response, "test-token", cookie_secure=True)
        response.set_cookie.assert_called_once_with(
            key=CSRF_COOKIE_NAME,
            value="test-token",
            httponly=True,
            samesite="lax",
            secure=True,
            path="/",
        )

    def test_sets_cookie_without_secure_flag(self) -> None:
        response = MagicMock()
        set_csrf_cookie(response, "test-token", cookie_secure=False)
        response.set_cookie.assert_called_once_with(
            key=CSRF_COOKIE_NAME,
            value="test-token",
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )


class TestValidateCsrf:
    def test_missing_cookie_returns_403(self) -> None:
        request = _make_request()
        form = FormData({"csrf_token": "some-token"})
        result = validate_csrf(request, form)
        assert result is not None
        assert result.status_code == 403

    def test_missing_form_field_returns_403(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: "token-value"})
        form = FormData({})
        result = validate_csrf(request, form)
        assert result is not None
        assert result.status_code == 403

    def test_mismatched_tokens_returns_403(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: "token-a"})
        form = FormData({CSRF_FORM_FIELD: "token-b"})
        result = validate_csrf(request, form)
        assert result is not None
        assert result.status_code == 403

    def test_matching_tokens_returns_none(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: "matching-token"})
        form = FormData({CSRF_FORM_FIELD: "matching-token"})
        result = validate_csrf(request, form)
        assert result is None

    def test_empty_cookie_returns_403(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: ""})
        form = FormData({CSRF_FORM_FIELD: ""})
        result = validate_csrf(request, form)
        assert result is not None
        assert result.status_code == 403
