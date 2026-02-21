"""Tests for the scoped HTTPException handler that returns JSON for protected API auth errors."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, PlainTextResponse, Response

from lobby.server.app import _make_auth_error_handler

_auth_error_handler = _make_auth_error_handler({"/rooms", "/servers", "/rooms/", "/servers/"})


def _make_request(path: str = "/rooms") -> object:
    """Build a minimal fake request with a url.path attribute."""

    class FakeURL:
        def __init__(self, path: str) -> None:
            self.path = path

    class FakeRequest:
        def __init__(self, path: str) -> None:
            self.url = FakeURL(path)

    return FakeRequest(path)


class TestAuthErrorHandler:
    async def test_401_on_rooms_returns_json(self) -> None:
        request = _make_request("/rooms")
        exc = HTTPException(status_code=401)

        result = await _auth_error_handler(request, exc)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 401
        assert result.body == b'{"error":"Authentication required"}'

    async def test_401_on_servers_returns_json(self) -> None:
        request = _make_request("/servers")
        exc = HTTPException(status_code=401)

        result = await _auth_error_handler(request, exc)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 401
        assert result.body == b'{"error":"Authentication required"}'

    async def test_401_on_non_api_path_returns_plain_text(self) -> None:
        request = _make_request("/some-other-page")
        exc = HTTPException(status_code=401)

        result = await _auth_error_handler(request, exc)

        assert isinstance(result, PlainTextResponse)
        assert result.status_code == 401

    async def test_404_returns_plain_text(self) -> None:
        request = _make_request("/rooms")
        exc = HTTPException(status_code=404, detail="Not Found")

        result = await _auth_error_handler(request, exc)

        assert isinstance(result, PlainTextResponse)
        assert result.status_code == 404
        assert result.body == b"Not Found"

    async def test_204_returns_empty_response(self) -> None:
        request = _make_request("/rooms")
        exc = HTTPException(status_code=204)

        result = await _auth_error_handler(request, exc)

        assert isinstance(result, Response)
        assert not isinstance(result, (JSONResponse, PlainTextResponse))
        assert result.status_code == 204

    async def test_304_returns_empty_response(self) -> None:
        request = _make_request("/servers")
        exc = HTTPException(status_code=304)

        result = await _auth_error_handler(request, exc)

        assert isinstance(result, Response)
        assert not isinstance(result, (JSONResponse, PlainTextResponse))
        assert result.status_code == 304

    async def test_500_returns_plain_text(self) -> None:
        request = _make_request("/rooms")
        exc = HTTPException(status_code=500, detail="Internal Server Error")

        result = await _auth_error_handler(request, exc)

        assert isinstance(result, PlainTextResponse)
        assert result.status_code == 500
        assert result.body == b"Internal Server Error"
