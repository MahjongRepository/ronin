"""Route auth policy helpers for fail-closed authorization.

Each helper wraps a route endpoint and sets the ``AUTH_POLICY_ATTR`` marker
so that startup validation can verify every route has an explicit auth policy.
"""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from starlette.authentication import has_required_scope, requires
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route

from shared.auth.models import AccountType

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from starlette.requests import Request
    from starlette.routing import BaseRoute

AUTH_POLICY_ATTR = "__auth_policy__"


def _login_redirect(request: Request) -> RedirectResponse:
    """Build a relative redirect to the login page preserving the original path."""
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    login_url = f"/login?{urlencode({'next': next_path})}"
    return RedirectResponse(url=login_url, status_code=303)


def protected_html(endpoint: Callable[..., Any]) -> Callable[..., Any]:
    """Require authentication; redirect unauthenticated users to login.

    Supports both sync and async endpoints.  Uses relative redirect URLs to
    prevent Host-header open redirect attacks.  Starlette's built-in
    ``requires(redirect=...)`` generates absolute URLs derived from the Host
    header, which an attacker can control.
    """
    if inspect.iscoroutinefunction(endpoint):

        @functools.wraps(endpoint)
        async def async_wrapper(request: Request, **kwargs: str) -> Response:
            if not has_required_scope(request, ["authenticated"]):
                return _login_redirect(request)
            return await endpoint(request, **kwargs)

        setattr(async_wrapper, AUTH_POLICY_ATTR, "protected_html")
        return async_wrapper

    @functools.wraps(endpoint)
    def sync_wrapper(request: Request, **kwargs: str) -> Response:
        if not has_required_scope(request, ["authenticated"]):
            return _login_redirect(request)
        return endpoint(request, **kwargs)

    setattr(sync_wrapper, AUTH_POLICY_ATTR, "protected_html")
    return sync_wrapper


def protected_api(endpoint: Callable[..., Any]) -> Callable[..., Any]:
    """Require authentication; raise 401 for unauthenticated API requests."""
    wrapped = requires("authenticated", status_code=401)(endpoint)
    setattr(wrapped, AUTH_POLICY_ATTR, "protected_api")
    return wrapped


def bot_only(endpoint: Callable[..., Any]) -> Callable[..., Any]:
    """Require authentication and bot account type.

    Returns 401 (via HTTPException) when unauthenticated.
    Returns 403 JSON when authenticated but not a bot account.
    """
    if inspect.iscoroutinefunction(endpoint):

        @functools.wraps(endpoint)
        async def async_wrapper(request: Request, **kwargs: str) -> Response:
            if not has_required_scope(request, ["authenticated"]):
                raise HTTPException(status_code=401)
            if request.user.account_type != AccountType.BOT:
                return JSONResponse({"error": "Bot account required"}, status_code=403)
            return await endpoint(request, **kwargs)

        setattr(async_wrapper, AUTH_POLICY_ATTR, "bot_only")
        return async_wrapper

    @functools.wraps(endpoint)
    def sync_wrapper(request: Request, **kwargs: str) -> Response:
        if not has_required_scope(request, ["authenticated"]):
            raise HTTPException(status_code=401)
        if request.user.account_type != AccountType.BOT:
            return JSONResponse({"error": "Bot account required"}, status_code=403)
        return endpoint(request, **kwargs)

    setattr(sync_wrapper, AUTH_POLICY_ATTR, "bot_only")
    return sync_wrapper


def public_route(endpoint: Callable[..., Any]) -> Callable[..., Any]:
    """Mark endpoint as explicitly public (no auth required).

    Returns a thin wrapper so the marker lives on the wrapper, not on the
    original callable.  This prevents accidental policy leakage when the
    same function object is reused on another route without wrapping.
    """
    if inspect.iscoroutinefunction(endpoint):

        @functools.wraps(endpoint)
        async def async_wrapper(request: Request, **kwargs: str) -> Response:
            return await endpoint(request, **kwargs)

        setattr(async_wrapper, AUTH_POLICY_ATTR, "public")
        return async_wrapper

    @functools.wraps(endpoint)
    def sync_wrapper(request: Request, **kwargs: str) -> Response:
        return endpoint(request, **kwargs)

    setattr(sync_wrapper, AUTH_POLICY_ATTR, "public")
    return sync_wrapper


_API_POLICIES = {"protected_api", "bot_only"}


def collect_protected_api_paths(routes: list[BaseRoute]) -> set[str]:
    """Return the set of path strings for routes marked ``protected_api`` or ``bot_only``."""
    paths: set[str] = set()
    for route in routes:
        if isinstance(route, Route) and getattr(route.endpoint, AUTH_POLICY_ATTR, None) in _API_POLICIES:
            paths.add(route.path)
    return paths


def validate_route_auth_policy(routes: list[BaseRoute]) -> None:
    """Verify every Route has an auth policy marker. Mount routes are exempt.

    Raises RuntimeError listing all unclassified routes if any are found.
    """
    unclassified: list[str] = []
    for route in routes:
        if isinstance(route, Mount):
            continue
        if isinstance(route, Route) and not hasattr(route.endpoint, AUTH_POLICY_ATTR):
            name = route.name or getattr(route.endpoint, "__name__", "unknown")
            unclassified.append(f"{route.path} ({name})")

    if unclassified:
        details = ", ".join(unclassified)
        msg = f"Unclassified routes missing auth policy: {details}"
        raise RuntimeError(msg)
