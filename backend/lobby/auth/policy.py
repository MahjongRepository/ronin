from __future__ import annotations

import functools
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from starlette.authentication import has_required_scope
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from shared.dal.models import AccountType

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.routing import BaseRoute

    type Endpoint = Callable[[Request], Awaitable[Response]]

AUTH_POLICY_ATTR = "__auth_policy__"


def _login_redirect(request: Request) -> RedirectResponse:
    """
    Build a relative redirect to the login page preserving the original path.
    """
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"

    login_url = f"/login?{urlencode({'next': next_path})}"
    return RedirectResponse(url=login_url, status_code=303)


def _unauthenticated() -> JSONResponse:
    return JSONResponse({"error": "Authentication required"}, status_code=HTTPStatus.UNAUTHORIZED)


def protected_html(endpoint: Endpoint) -> Endpoint:
    """
    Require authentication; redirect unauthenticated users to login.

    Uses relative redirect URLs to prevent Host-header open redirect attacks. Starlette's built-in
    ``requires(redirect=...)`` generates absolute URLs derived from the Host header, which an attacker can control.
    """

    @functools.wraps(endpoint)
    async def wrapper(request: Request) -> Response:
        if not has_required_scope(request, ["authenticated"]):
            return _login_redirect(request)

        return await endpoint(request)

    setattr(wrapper, AUTH_POLICY_ATTR, "protected_html")
    return wrapper


def bot_only(endpoint: Endpoint) -> Endpoint:
    """
    Require authentication and bot account type.

    Return a JSON 401 when unauthenticated and a JSON 403 when authenticated but not a bot account.
    """

    @functools.wraps(endpoint)
    async def wrapper(request: Request) -> Response:
        if not has_required_scope(request, ["authenticated"]):
            return _unauthenticated()

        if request.user.account_type != AccountType.BOT:
            return JSONResponse({"error": "Bot account required"}, status_code=HTTPStatus.FORBIDDEN)

        return await endpoint(request)

    setattr(wrapper, AUTH_POLICY_ATTR, "bot_only")
    return wrapper


def public_route(endpoint: Endpoint) -> Endpoint:
    """
    Mark endpoint as explicitly public (no auth required).

    Returns a thin wrapper so the marker lives on the wrapper, not on the original callable.  This prevents accidental
    policy leakage when the same function object is reused on another route without wrapping.
    """

    @functools.wraps(endpoint)
    async def wrapper(request: Request) -> Response:
        return await endpoint(request)

    setattr(wrapper, AUTH_POLICY_ATTR, "public")
    return wrapper


def validate_route_auth_policy(routes: list[BaseRoute]) -> None:
    """
    Verify every Route has an auth policy marker.

    Mount and other non-Route entries are exempt. Raise RuntimeError listing all unclassified routes if any are found.
    """
    unclassified: list[str] = []
    for route in routes:
        if isinstance(route, Route) and not hasattr(route.endpoint, AUTH_POLICY_ATTR):
            name = route.name or getattr(route.endpoint, "__name__", "unknown")
            unclassified.append(f"{route.path} ({name})")

    if unclassified:
        details = ", ".join(unclassified)
        msg = f"Unclassified routes missing auth policy: {details}"
        raise RuntimeError(msg)
