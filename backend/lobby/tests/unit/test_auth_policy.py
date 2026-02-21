"""Tests for auth policy helpers and route validation."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from starlette.applications import Starlette
from starlette.authentication import AuthCredentials
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

from lobby.auth.policy import (
    collect_protected_api_paths,
    protected_api,
    protected_html,
    public_route,
    validate_route_auth_policy,
)


async def _login_page(request: Request) -> JSONResponse:
    return JSONResponse({"page": "login"})


# Minimal app attached to the request scope for route resolution.
_app = Starlette(routes=[Route("/login", _login_page, name="login_page")])


def _make_request(
    *,
    authenticated: bool,
    path: str = "/some-page",
    query_string: bytes = b"",
) -> Request:
    """Build a real Starlette Request with auth scopes pre-set."""
    scopes = ["authenticated"] if authenticated else []
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query_string,
        "headers": [],
        "root_path": "",
        "server": ("testserver", 80),
        "scheme": "http",
        "app": _app,
        "auth": AuthCredentials(scopes),
    }
    return Request(scope)


async def _dummy_handler(request: Request) -> str:
    return "ok"


def _sync_dummy_handler(request: Request) -> str:
    return "ok"


class TestProtectedHtml:
    async def test_unauthenticated_redirects_to_login(self) -> None:
        wrapped = protected_html(_dummy_handler)
        request = _make_request(authenticated=False)

        result = await wrapped(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        location = dict(result.headers)["location"]
        assert "/login" in location
        assert "next=" in location

    async def test_redirect_preserves_query_string(self) -> None:
        wrapped = protected_html(_dummy_handler)
        request = _make_request(authenticated=False, path="/page", query_string=b"tab=settings")

        result = await wrapped(request)

        assert isinstance(result, RedirectResponse)
        location = dict(result.headers)["location"]
        parsed = urlparse(location)
        assert parsed.path == "/login"
        query = parse_qs(parsed.query)
        assert "/page?tab=settings" in query["next"]

    async def test_authenticated_passes_through(self) -> None:
        wrapped = protected_html(_dummy_handler)
        request = _make_request(authenticated=True)

        result = await wrapped(request)

        assert result == "ok"

    def test_sync_authenticated_passes_through(self) -> None:
        wrapped = protected_html(_sync_dummy_handler)
        request = _make_request(authenticated=True)

        result = wrapped(request)

        assert result == "ok"

    def test_sync_unauthenticated_redirects_to_login(self) -> None:
        wrapped = protected_html(_sync_dummy_handler)
        request = _make_request(authenticated=False)

        result = wrapped(request)

        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        location = dict(result.headers)["location"]
        assert "/login" in location
        assert "next=" in location


class TestProtectedApi:
    async def test_unauthenticated_raises_401(self) -> None:
        wrapped = protected_api(_dummy_handler)
        request = _make_request(authenticated=False)

        with pytest.raises(HTTPException) as exc_info:
            await wrapped(request)

        assert exc_info.value.status_code == 401

    async def test_authenticated_passes_through(self) -> None:
        wrapped = protected_api(_dummy_handler)
        request = _make_request(authenticated=True)

        result = await wrapped(request)

        assert result == "ok"


class TestPublicRoute:
    async def test_does_not_block_unauthenticated(self) -> None:
        wrapped = public_route(_dummy_handler)
        request = _make_request(authenticated=False)

        result = await wrapped(request)

        assert result == "ok"

    def test_sync_does_not_block_unauthenticated(self) -> None:
        wrapped = public_route(_sync_dummy_handler)
        request = _make_request(authenticated=False)

        result = wrapped(request)

        assert result == "ok"


def _make_handler() -> object:
    """Return a fresh async handler with no attributes from prior tests."""

    async def handler(request: Request) -> str:
        return "ok"

    return handler


class TestValidateRouteAuthPolicy:
    def test_all_routes_classified_passes(self) -> None:
        routes = [
            Route("/a", public_route(_make_handler()), methods=["GET"], name="a"),
            Route("/b", protected_api(_make_handler()), methods=["GET"], name="b"),
        ]

        validate_route_auth_policy(routes)

    def test_unclassified_route_raises_runtime_error(self) -> None:
        routes = [
            Route("/ok", public_route(_make_handler()), methods=["GET"], name="ok"),
            Route("/bad", _make_handler(), methods=["GET"], name="bad"),
        ]

        with pytest.raises(RuntimeError, match="Unclassified routes"):
            validate_route_auth_policy(routes)

    def test_error_message_includes_path_and_name(self) -> None:
        routes = [
            Route("/missing", _make_handler(), methods=["GET"], name="missing_route"),
        ]

        with pytest.raises(RuntimeError, match=r"/missing \(missing_route\)"):
            validate_route_auth_policy(routes)

    def test_mount_is_exempt(self) -> None:
        routes = [
            Route("/a", public_route(_make_handler()), methods=["GET"], name="a"),
            Mount("/static", app=Starlette(), name="static"),
        ]

        validate_route_auth_policy(routes)

    def test_multiple_unclassified_routes_all_reported(self) -> None:
        routes = [
            Route("/x", _make_handler(), methods=["GET"], name="x"),
            Route("/y", _make_handler(), methods=["POST"], name="y"),
        ]

        with pytest.raises(RuntimeError, match="/x") as exc_info:
            validate_route_auth_policy(routes)
        assert "/y" in str(exc_info.value)


class TestCollectProtectedApiPaths:
    def test_collects_only_protected_api_paths(self) -> None:
        routes = [
            Route("/rooms", protected_api(_make_handler()), methods=["GET"], name="rooms"),
            Route("/servers", protected_api(_make_handler()), methods=["GET"], name="servers"),
            Route("/", protected_html(_make_handler()), methods=["GET"], name="index"),
            Route("/health", public_route(_make_handler()), methods=["GET"], name="health"),
        ]

        result = collect_protected_api_paths(routes)

        assert result == {"/rooms", "/servers"}

    def test_ignores_mounts(self) -> None:
        routes = [
            Route("/rooms", protected_api(_make_handler()), methods=["GET"], name="rooms"),
            Mount("/static", app=Starlette(), name="static"),
        ]

        result = collect_protected_api_paths(routes)

        assert result == {"/rooms"}
