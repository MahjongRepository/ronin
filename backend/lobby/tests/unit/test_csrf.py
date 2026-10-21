from __future__ import annotations

from unittest.mock import MagicMock

from starlette.datastructures import FormData

from lobby.auth.csrf import (
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
    def test_get_or_create_csrf_token__when_cookie_present__should_return_existing_token(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: "existing-token"})
        token, is_new = get_or_create_csrf_token(request)
        assert token == "existing-token"
        assert is_new is False

    def test_get_or_create_csrf_token__when_no_cookie__should_generate_new_token(self) -> None:
        request = _make_request()
        token, is_new = get_or_create_csrf_token(request)
        assert len(token) > 0
        assert is_new is True

    def test_get_or_create_csrf_token__when_called_twice_without_cookie__should_generate_unique_tokens(self) -> None:
        request = _make_request()
        token1, _ = get_or_create_csrf_token(request)
        token2, _ = get_or_create_csrf_token(request)
        assert token1 != token2


class TestSetCsrfCookie:
    def test_set_csrf_cookie__when_secure__should_set_secure_flag(self) -> None:
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

    def test_set_csrf_cookie__when_not_secure__should_omit_secure_flag(self) -> None:
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
    def test_validate_csrf__when_cookie_missing__should_return_403(self) -> None:
        request = _make_request()
        form = FormData({"csrf_token": "some-token"})
        result = validate_csrf(request, form)
        assert result is not None
        assert result.status_code == 403

    def test_validate_csrf__when_form_field_missing__should_return_403(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: "token-value"})
        form = FormData({})
        result = validate_csrf(request, form)
        assert result is not None
        assert result.status_code == 403

    def test_validate_csrf__when_tokens_mismatch__should_return_403(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: "token-a"})
        form = FormData({CSRF_FORM_FIELD: "token-b"})
        result = validate_csrf(request, form)
        assert result is not None
        assert result.status_code == 403

    def test_validate_csrf__when_tokens_match__should_return_none(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: "matching-token"})
        form = FormData({CSRF_FORM_FIELD: "matching-token"})
        result = validate_csrf(request, form)
        assert result is None

    def test_validate_csrf__when_cookie_empty__should_return_403(self) -> None:
        request = _make_request({CSRF_COOKIE_NAME: ""})
        form = FormData({CSRF_FORM_FIELD: ""})
        result = validate_csrf(request, form)
        assert result is not None
        assert result.status_code == 403
