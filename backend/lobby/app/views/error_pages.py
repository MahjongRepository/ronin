from __future__ import annotations

from enum import StrEnum
from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, PlainTextResponse, Response

from app.auth.csrf import get_or_create_csrf_token, is_cross_site_post, is_csrf_valid, set_csrf_cookie
from app.views.assets import render_page, same_origin_referer_path

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.datastructures import FormData
    from starlette.requests import Request

    from app.auth.settings import AuthSettings


class ErrorCode(StrEnum):
    """
    The failure an error page names; the lobby app words it from the code in the page's language.
    """

    NOT_FOUND = "not_found"
    SERVER = "server"
    REFUSED = "refused"
    SESSION_EXPIRED = "session_expired"


_LOBBY_PATH = "/"
NO_STORE_HEADERS = {"Cache-Control": "no-store"}


def validate_csrf(request: Request, form_data: FormData) -> Response | None:
    """
    Check that the form CSRF token matches the cookie token.

    Return the 403 "session expired" page on failure, or None if the token is valid. Bot API routes (JSON + API key)
    skip this check: they do not authenticate with cookies.
    """
    if is_csrf_valid(request, form_data):
        return None

    return _session_expired_page(request)


def json_csrf_rejection(request: Request) -> Response:
    """
    Answer a failed CSRF check on a JSON route with 403 ``csrf_invalid`` and the token a single retry must send.

    The token is the cookie's, or a new one set as the cookie under ``render_page``'s rule: never on a POST from another
    site, which arrives without the cookie the browser holds.
    """
    token, is_new = get_or_create_csrf_token(request)
    response = JSONResponse(
        {"error": "csrf_invalid", "csrf_token": token}, status_code=HTTPStatus.FORBIDDEN, headers=NO_STORE_HEADERS
    )
    if is_new and not is_cross_site_post(request):
        auth_settings: AuthSettings = request.app.state.auth_settings
        set_csrf_cookie(response, token=token, cookie_secure=auth_settings.cookie_secure)

    return response


async def http_error_page(request: Request, exc: Exception) -> Response:
    """
    Answer an HTTP error with the styled error page for a browser, and Starlette's plain text otherwise.

    Only a server error (5xx) tells the user to try again: a refused request fails the same way the next time. The page
    names the failure by its status class; ``detail``, written for logs, stays in the plain-text answer.
    """
    assert isinstance(exc, HTTPException)  # noqa: S101 - registered for HTTPException only
    if exc.status_code in {HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED}:
        return Response(status_code=exc.status_code, headers=exc.headers)

    if not _wants_html(request):
        return PlainTextResponse(exc.detail, status_code=exc.status_code, headers=exc.headers)

    if exc.status_code == HTTPStatus.NOT_FOUND:
        code = ErrorCode.NOT_FOUND
    elif exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        code = ErrorCode.SERVER
    else:
        code = ErrorCode.REFUSED

    return _render_error_page(request, status_code=exc.status_code, code=code, headers=exc.headers)


async def server_error_page(request: Request, _exc: Exception) -> Response:
    """
    Answer an unhandled exception (logged by the server) with the styled 500 page for a browser.
    """
    if not _wants_html(request):
        return PlainTextResponse("Internal Server Error", status_code=HTTPStatus.INTERNAL_SERVER_ERROR)

    return _render_error_page(request, status_code=HTTPStatus.INTERNAL_SERVER_ERROR, code=ErrorCode.SERVER)


def _session_expired_page(request: Request) -> Response:
    """
    Render the 403 page for a failed CSRF check: the form was stale, so reloading the page it came from fixes it.
    """
    return _render_error_page(
        request,
        status_code=HTTPStatus.FORBIDDEN,
        code=ErrorCode.SESSION_EXPIRED,
        action_href=same_origin_referer_path(request) or _LOBBY_PATH,
    )


def _render_error_page(
    request: Request,
    *,
    status_code: int,
    code: ErrorCode,
    action_href: str = _LOBBY_PATH,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """
    Render ``error.html`` with the status, the error code and the action's link for the lobby app to word.
    """
    return render_page(
        request,
        template_name="error.html",
        context={"status_code": status_code, "error_code": code.value, "action_href": action_href},
        status_code=status_code,
        headers=headers,
    )


def _wants_html(request: Request) -> bool:
    """
    Return whether the client is a browser navigating to a page; API clients and asset loads keep the plain answer.
    """
    return "text/html" in request.headers.get("accept", "")
