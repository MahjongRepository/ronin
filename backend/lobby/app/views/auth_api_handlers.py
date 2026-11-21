from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from app.auth.csrf import is_csrf_valid
from app.auth.service import AuthError, AuthErrorCode
from app.views.auth_handlers import parse_next_path, set_session_cookie
from app.views.error_pages import NO_STORE_HEADERS, json_csrf_rejection
from app.views.json_body import parse_json_body

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from app.auth.service import AuthService

_FIELD_OF_AUTH_ERROR = {
    AuthErrorCode.USERNAME_TAKEN: "username",
    AuthErrorCode.USERNAME_LENGTH: "username",
    AuthErrorCode.USERNAME_PATTERN: "username",
    AuthErrorCode.USERNAME_RESERVED_PREFIX: "username",
    AuthErrorCode.PASSWORD_LENGTH: "password",
    AuthErrorCode.PASSWORD_BYTES: "password",
}


def _error_answer(payload: dict[str, object], status_code: HTTPStatus = HTTPStatus.BAD_REQUEST) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=NO_STORE_HEADERS)


def _auth_error_answer(error: AuthError) -> JSONResponse:
    """
    Answer an auth failure by its code, the params its text interpolates and the form field it concerns, if any.
    """
    return _error_answer(
        {
            "error": "auth_error",
            "code": error.code,
            "params": error.params,
            "field": _FIELD_OF_AUTH_ERROR.get(error.code),
        }
    )


def _signed_in_answer(request: Request, *, token: str, next_value: object) -> JSONResponse:
    """
    Answer a successful sign-in with the page to open next and the new session cookie.
    """
    response = JSONResponse({"next": parse_next_path(next_value) or "/"}, headers=NO_STORE_HEADERS)
    set_session_cookie(response, token=token, auth_settings=request.app.state.auth_settings)
    return response


async def _read_credentials(request: Request, *fields: str) -> dict | Response:
    """
    Read a JSON auth body whose ``fields`` are all strings, then check its CSRF header; answer the failure otherwise.
    """
    body = await parse_json_body(request)
    if body is None or not all(isinstance(body.get(field), str) for field in fields):
        return _error_answer({"error": "invalid_body"})

    if not is_csrf_valid(request):
        return json_csrf_rejection(request)

    return body


async def api_login(request: Request) -> Response:
    """
    POST /api/lobby/auth/login - check the credentials and start a session.
    """
    body = await _read_credentials(request, "username", "password")
    if not isinstance(body, dict):
        return body

    auth_service: AuthService = request.app.state.auth_service
    try:
        _, token = await auth_service.login(
            body["username"], body["password"], replacing=request.cookies.get("session_id")
        )
    except AuthError as e:
        return _auth_error_answer(e)

    return _signed_in_answer(request, token=token, next_value=body.get("next"))


async def api_register(request: Request) -> Response:
    """
    POST /api/lobby/auth/register - create an account and start its session.
    """
    body = await _read_credentials(request, "username", "password", "confirm_password")
    if not isinstance(body, dict):
        return body

    username, password = body["username"], body["password"]
    if password != body["confirm_password"]:
        return _error_answer({"error": "passwords_mismatch", "field": "confirm_password"})

    auth_service: AuthService = request.app.state.auth_service
    try:
        await auth_service.register(username, password)
        _, token = await auth_service.login(username, password, replacing=request.cookies.get("session_id"))
    except AuthError as e:
        return _auth_error_answer(e)

    return _signed_in_answer(request, token=token, next_value=body.get("next"))


async def api_guest_login(request: Request) -> Response:
    """
    POST /api/lobby/auth/guest - start a guest session; a signed-in user keeps the session they have.
    """
    body = await _read_credentials(request)
    if not isinstance(body, dict):
        return body

    next_value = body.get("next")
    if request.user.is_authenticated:
        return JSONResponse({"next": parse_next_path(next_value) or "/"}, headers=NO_STORE_HEADERS)

    client_ip = request.client.host if request.client else ""
    if not request.app.state.guest_login_limiter.consume(client_ip):
        return _error_answer({"error": "guest_rate_limited"}, status_code=HTTPStatus.TOO_MANY_REQUESTS)

    auth_service: AuthService = request.app.state.auth_service
    _, token = await auth_service.login_as_guest(replacing=request.cookies.get("session_id"))
    return _signed_in_answer(request, token=token, next_value=next_value)
