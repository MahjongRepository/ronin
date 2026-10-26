from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

_FONTS_FONT_SRC = "font-src 'self' https://fonts.gstatic.com; "

_COMMON_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
]


def _build_csp_headers(
    vite_dev_url: str,
) -> tuple[
    list[tuple[bytes, bytes]],  # lobby (default — all non-game pages)
    list[tuple[bytes, bytes]],  # game
]:
    """
    Build path-specific CSP header sets.

    Two tiers:
    - Lobby (all non-game pages, including rooms): scripts + same-origin connect
    - Game: scripts + external WebSocket connect

    When vite_dev_url is set, both tiers also allow scripts and WebSocket from that origin.
    """
    vite_script = ""
    vite_connect = ""
    vite_style = ""
    vite_img = ""
    if vite_dev_url:
        parsed = urlparse(vite_dev_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_origin = f"{ws_scheme}://{parsed.netloc}"

        vite_script = f" {vite_dev_url}"
        vite_connect = f" {vite_dev_url} {ws_origin}"
        vite_style = f" {vite_dev_url}"
        vite_img = f"img-src 'self' {vite_dev_url}; "

    fonts_style_src = f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com{vite_style}; "

    # Lobby pages (including rooms): scripts + same-origin WS
    lobby_csp = (
        "default-src 'self'; "
        f"script-src 'self'{vite_script}; "
        + fonts_style_src
        + _FONTS_FONT_SRC
        + vite_img
        + f"connect-src 'self'{vite_connect}; "
        + "frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    )

    # Game pages: scripts + external WS
    game_csp = (
        "default-src 'self'; "
        f"script-src 'self'{vite_script}; "
        + fonts_style_src
        + _FONTS_FONT_SRC
        + vite_img
        + f"connect-src 'self' ws: wss:{vite_connect}; "
        + "frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    )

    return (
        [*_COMMON_HEADERS, (b"content-security-policy", lobby_csp.encode())],
        [*_COMMON_HEADERS, (b"content-security-policy", game_csp.encode())],
    )


class SecurityHeadersMiddleware:
    """
    Inject standard security headers into every HTTP response.

    Game paths (/play/*, /game-assets/) get a CSP that allows scripts and external WebSocket. All other paths (lobby,
    rooms, auth) get a CSP that allows scripts and same-origin WebSocket.
    """

    def __init__(self, app: ASGIApp, *, vite_dev_url: str = "") -> None:
        self.app = app
        self._lobby_headers, self._game_headers = _build_csp_headers(vite_dev_url)

    def _get_csp_headers(self, path: str) -> list[tuple[bytes, bytes]]:
        if path.startswith(("/play/", "/game-assets/")):
            return self._game_headers

        return self._lobby_headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        extra_headers = self._get_csp_headers(scope["path"])

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(extra_headers)
                message["headers"] = headers

            await send(message)

        await self.app(scope, receive, send_with_headers)


class _RequestBodyTooLargeError(Exception):
    pass


class RequestBodyLimitMiddleware:
    """
    Cap every HTTP request body at ``max_body_size`` bytes, and end a request quietly when its client disconnects.

    It counts the bytes the app reads from ``receive``, so a chunked upload without ``Content-Length`` is capped as
    well. Every lobby body (the form posts and the bot JSON API) is a few hundred bytes, and every handler reads its
    body before acting, so an excess is answered 413 with no side effect. A small cap also keeps bot JSON far below the
    nesting depth at which the JSON parser raises ``RecursionError``. A body read that finds the client gone raises
    ``ClientDisconnect``; that is not a server error and nobody is left to read a response, so none is sent.

    Once the response has started, frames pass through uncounted: a ``FileResponse`` reads ``receive`` while it streams,
    only to notice a disconnect, and a 413 can no longer be sent. The 413 gets the security headers because this sits
    inside ``SecurityHeadersMiddleware``. Starlette's own ``RequestBodyLimitMiddleware`` does not fit: its 413 is plain
    text where the bot API answers JSON, it re-raises an excess found after the response started, and it lets
    ``ClientDisconnect`` escape as a server error.
    """

    def __init__(self, app: ASGIApp, *, max_body_size: int) -> None:
        self.app = app
        self._max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        received = 0
        response_started = False

        async def receive_within_limit() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request" and not response_started:
                received += len(message.get("body", b""))
                if received > self._max_body_size:
                    raise _RequestBodyTooLargeError

            return message

        async def send_noting_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True

            await send(message)

        try:
            await self.app(scope, receive_within_limit, send_noting_start)
        except _RequestBodyTooLargeError:
            response = JSONResponse(
                {"error": "Request body too large"}, status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )
            await response(scope, receive, send)
        except ClientDisconnect:
            return


class SlashNormalizationMiddleware:
    """
    Strip trailing slashes so that /path/ is handled the same as /path.

    Without this, Starlette's default ``redirect_slashes=True`` responds with a 307 redirect for the trailing-slash
    variant.  That redirect bypasses authentication middleware, which means unauthenticated requests to ``/api/rooms/``
    would get a redirect instead of a 401.

    Applied as ASGI middleware, it rewrites the path *before* routing, eliminating the need for duplicate trailing-slash
    route definitions.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path: str = scope["path"]
            if len(path) > 1 and path.endswith("/"):
                scope["path"] = path.rstrip("/")

        await self.app(scope, receive, send)
