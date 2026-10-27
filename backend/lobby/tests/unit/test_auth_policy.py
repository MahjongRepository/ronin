from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from starlette.applications import Starlette
from starlette.authentication import AuthCredentials
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

from lobby.auth.models import AuthenticatedPlayer
from lobby.auth.policy import (
    bot_only,
    protected_html,
    protected_json,
    public_route,
    validate_route_auth_policy,
)
from shared.dal.models import AccountType


async def _login_page(request: Request) -> JSONResponse:
    return JSONResponse({"page": "login"})


# Minimal app attached to the request scope for route resolution.
_app = Starlette(routes=[Route("/login", _login_page, name="login_page")])


def _make_request(
    *,
    authenticated: bool,
    method: str = "GET",
    path: str = "/some-page",
    query_string: bytes = b"",
    account_type: AccountType = AccountType.HUMAN,
) -> Request:
    scopes = ["authenticated"] if authenticated else []
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": [],
        "root_path": "",
        "server": ("testserver", 80),
        "scheme": "http",
        "app": _app,
        "auth": AuthCredentials(scopes),
    }
    if authenticated:
        scope["user"] = AuthenticatedPlayer(user_id="test-id", username="test", account_type=account_type)

    return Request(scope)


async def _dummy_handler(request: Request) -> str:
    return "ok"


class TestProtectedHtml:
    async def test_protected_html__when_unauthenticated__should_redirect_to_login(self):
        wrapped = protected_html(_dummy_handler)
        request = _make_request(authenticated=False)

        result = await wrapped(request)
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 303
        location = dict(result.headers)["location"]
        assert "/login" in location
        assert "next=" in location

    async def test_protected_html__when_unauthenticated_with_query__should_preserve_it_in_next(self):
        wrapped = protected_html(_dummy_handler)
        request = _make_request(authenticated=False, path="/page", query_string=b"tab=settings")

        result = await wrapped(request)
        assert isinstance(result, RedirectResponse)
        location = dict(result.headers)["location"]
        parsed = urlparse(location)
        assert parsed.path == "/login"
        query = parse_qs(parsed.query)
        assert "/page?tab=settings" in query["next"]

    async def test_protected_html__when_unauthenticated_post__should_redirect_to_login_without_next(self):
        wrapped = protected_html(_dummy_handler)
        request = _make_request(authenticated=False, method="POST", path="/rooms/r1/join")

        result = await wrapped(request)
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/login"

    async def test_protected_html__when_authenticated__should_call_handler(self):
        wrapped = protected_html(_dummy_handler)
        request = _make_request(authenticated=True)

        result = await wrapped(request)
        assert result == "ok"


class TestProtectedJson:
    async def test_protected_json__when_unauthenticated__should_return_401_instead_of_a_redirect(self):
        wrapped = protected_json(_dummy_handler)
        request = _make_request(authenticated=False)

        result = await wrapped(request)
        assert result.status_code == 401
        assert result.body == b'{"error":"Authentication required"}'

    @pytest.mark.parametrize("account_type", [AccountType.HUMAN, AccountType.BOT])
    async def test_protected_json__when_authenticated__should_call_handler_for_either_account_type(self, account_type):
        wrapped = protected_json(_dummy_handler)
        request = _make_request(authenticated=True, account_type=account_type)

        result = await wrapped(request)
        assert result == "ok"


class TestBotOnly:
    async def test_bot_only__when_unauthenticated__should_return_401(self):
        wrapped = bot_only(_dummy_handler)
        request = _make_request(authenticated=False)

        result = await wrapped(request)
        assert result.status_code == 401
        assert result.body == b'{"error":"Authentication required"}'

    async def test_bot_only__when_human__should_return_403(self):
        wrapped = bot_only(_dummy_handler)
        request = _make_request(authenticated=True, account_type=AccountType.HUMAN)

        result = await wrapped(request)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 403

    async def test_bot_only__when_bot__should_call_handler(self):
        wrapped = bot_only(_dummy_handler)
        request = _make_request(authenticated=True, account_type=AccountType.BOT)

        result = await wrapped(request)
        assert result == "ok"


def _make_handler() -> object:
    async def handler(request: Request) -> str:
        return "ok"

    return handler


class TestValidateRouteAuthPolicy:
    def test_validate_route_auth_policy__when_route_unclassified__should_raise_runtime_error(self):
        routes = [
            Route("/ok", public_route(_make_handler()), methods=["GET"], name="ok"),
            Route("/bad", _make_handler(), methods=["GET"], name="bad"),
        ]
        with pytest.raises(RuntimeError, match="Unclassified routes"):
            validate_route_auth_policy(routes)

    def test_validate_route_auth_policy__when_mount_present__should_exempt_it(self):
        routes = [
            Route("/a", public_route(_make_handler()), methods=["GET"], name="a"),
            Mount("/static", app=Starlette(), name="static"),
        ]
        validate_route_auth_policy(routes)

    def test_validate_route_auth_policy__when_several_routes_unclassified__should_report_all(self):
        routes = [
            Route("/x", _make_handler(), methods=["GET"], name="x"),
            Route("/y", _make_handler(), methods=["POST"], name="y"),
        ]
        with pytest.raises(RuntimeError, match="/x") as exc_info:
            validate_route_auth_policy(routes)
        assert "/y" in str(exc_info.value)
