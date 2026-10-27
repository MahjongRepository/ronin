from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse, Response

from lobby.auth.csrf import is_csrf_valid
from lobby.views.assets import render_page

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.datastructures import FormData
    from starlette.requests import Request


@dataclass(frozen=True)
class _ErrorPage:
    """
    The heading and the sentence of a styled error page.
    """

    title: str
    message: str


_NOT_FOUND = _ErrorPage("Page not found", "Nothing lives at this address. It may have moved.")
_SERVER_FAILURE = _ErrorPage("Something went wrong", "The server could not finish this request. Try again in a moment.")
_REQUEST_REFUSED_MESSAGE = "The server could not accept this request."
_SESSION_EXPIRED = _ErrorPage("Session expired", "Nothing was sent: the page was out of date. Reload it and try again.")
_LOBBY_PATH = "/"
_BACK_TO_LOBBY = "Back to lobby"


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

    Only a server error (5xx) tells the user to try again: a refused request fails the same way the next time.
    """
    assert isinstance(exc, HTTPException)  # noqa: S101 - registered for HTTPException only
    if exc.status_code in {HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED}:
        return Response(status_code=exc.status_code, headers=exc.headers)

    if not _wants_html(request):
        return PlainTextResponse(exc.detail, status_code=exc.status_code, headers=exc.headers)

    if exc.status_code == HTTPStatus.NOT_FOUND:
        page = _NOT_FOUND
    elif exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        page = _ErrorPage(exc.detail, _SERVER_FAILURE.message)
    else:
        page = _ErrorPage(exc.detail, _REQUEST_REFUSED_MESSAGE)

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
    back_path = _same_origin_referer_path(request)
    return _render_error_page(
        request,
        status_code=HTTPStatus.FORBIDDEN,
        page=_SESSION_EXPIRED,
        action_href=back_path or _LOBBY_PATH,
        action_label="Reload the page" if back_path else _BACK_TO_LOBBY,
    )


def _render_error_page(  # noqa: PLR0913
    request: Request,
    *,
    status_code: int,
    page: _ErrorPage,
    action_href: str = _LOBBY_PATH,
    action_label: str = _BACK_TO_LOBBY,
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
            "title": page.title,
            "message": page.message,
            "action_href": action_href,
            "action_label": action_label,
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


def _same_origin_referer_path(request: Request) -> str | None:
    """
    Return the path and query of the page that posted the form, or None when it is missing, malformed or off-site.

    Leading slashes and backslashes collapse to one slash: a browser reads ``//host/x`` and ``/\\host/x`` alike as a
    link to another host.
    """
    referer = request.headers.get("referer")
    if not referer:
        return None

    try:
        parsed = urlsplit(referer)
    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"} or parsed.netloc != request.url.netloc:
        return None

    path = "/" + parsed.path.lstrip("/\\")
    return f"{path}?{parsed.query}" if parsed.query else path
