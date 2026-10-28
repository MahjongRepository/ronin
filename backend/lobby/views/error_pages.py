from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse, Response

from lobby.auth.csrf import is_csrf_valid
from lobby.views.assets import render_page, same_origin_referer_path, translate_for_request

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.datastructures import FormData
    from starlette.requests import Request


@dataclass(frozen=True)
class _ErrorPage:
    """
    The catalog keys of the heading and the sentence of a styled error page.
    """

    title_key: str
    message_key: str


_NOT_FOUND = _ErrorPage("error.not_found.title", "error.not_found.message")
_SERVER_FAILURE = _ErrorPage("error.server.title", "error.server.message")
_REQUEST_REFUSED = _ErrorPage("error.refused.title", "error.refused.message")
_SESSION_EXPIRED = _ErrorPage("error.session_expired.title", "error.session_expired.message")
_LOBBY_PATH = "/"
_BACK_TO_LOBBY_KEY = "common.back_to_lobby"
_RELOAD_PAGE_KEY = "error.reload_page"


def validate_csrf(request: Request, form_data: FormData) -> Response | None:
    """
    Check that the form CSRF token matches the cookie token.

    Return the 403 "session expired" page on failure, or None if the token is valid. Bot API routes (JSON + API key)
    skip this check: they do not authenticate with cookies.
    """
    if is_csrf_valid(request, form_data):
        return None

    return _session_expired_page(request)


async def http_error_page(request: Request, exc: Exception) -> Response:
    """
    Answer an HTTP error with the styled error page for a browser, and Starlette's plain text otherwise.

    Only a server error (5xx) tells the user to try again: a refused request fails the same way the next time. The page
    names the failure by its status class in the user's language; ``detail``, written for logs, stays in the plain-text
    answer.
    """
    assert isinstance(exc, HTTPException)  # noqa: S101 - registered for HTTPException only
    if exc.status_code in {HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED}:
        return Response(status_code=exc.status_code, headers=exc.headers)

    if not _wants_html(request):
        return PlainTextResponse(exc.detail, status_code=exc.status_code, headers=exc.headers)

    if exc.status_code == HTTPStatus.NOT_FOUND:
        page = _NOT_FOUND
    elif exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        page = _SERVER_FAILURE
    else:
        page = _REQUEST_REFUSED

    return _render_error_page(request, status_code=exc.status_code, page=page, headers=exc.headers)


async def server_error_page(request: Request, _exc: Exception) -> Response:
    """
    Answer an unhandled exception (logged by the server) with the styled 500 page for a browser.
    """
    if not _wants_html(request):
        return PlainTextResponse("Internal Server Error", status_code=HTTPStatus.INTERNAL_SERVER_ERROR)

    return _render_error_page(request, status_code=HTTPStatus.INTERNAL_SERVER_ERROR, page=_SERVER_FAILURE)


def _session_expired_page(request: Request) -> Response:
    """
    Render the 403 page for a failed CSRF check: the form was stale, so reloading the page it came from fixes it.
    """
    back_path = same_origin_referer_path(request)
    return _render_error_page(
        request,
        status_code=HTTPStatus.FORBIDDEN,
        page=_SESSION_EXPIRED,
        action_href=back_path or _LOBBY_PATH,
        action_label_key=_RELOAD_PAGE_KEY if back_path else _BACK_TO_LOBBY_KEY,
    )


def _render_error_page(  # noqa: PLR0913
    request: Request,
    *,
    status_code: int,
    page: _ErrorPage,
    action_href: str = _LOBBY_PATH,
    action_label_key: str = _BACK_TO_LOBBY_KEY,
    headers: Mapping[str, str] | None = None,
) -> Response:
    """
    Render ``error.html`` for the page, with the navigation of the user signed in, if any.

    The user comes from the scope, not ``request.user``: an error raised before authentication ran leaves none there.
    """
    user = request.scope.get("user")
    return render_page(
        request,
        template_name="error.html",
        context={
            "status_code": status_code,
            "title": translate_for_request(request, page.title_key),
            "message": translate_for_request(request, page.message_key),
            "action_href": action_href,
            "action_label": translate_for_request(request, action_label_key),
            "username": user.username if user is not None and user.is_authenticated else None,
        },
        status_code=status_code,
        headers=headers,
    )


def _wants_html(request: Request) -> bool:
    """
    Return whether the client is a browser navigating to a page; API clients and asset loads keep the plain answer.
    """
    return "text/html" in request.headers.get("accept", "")
