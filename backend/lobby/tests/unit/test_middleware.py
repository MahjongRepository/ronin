"""Tests for SlashNormalizationMiddleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from lobby.server.middleware import SlashNormalizationMiddleware

if TYPE_CHECKING:
    from starlette.requests import Request


async def _echo_path(request: Request) -> JSONResponse:
    return JSONResponse({"path": request.url.path})


def _make_app() -> Starlette:
    app = Starlette(
        routes=[Route("/items", _echo_path, methods=["GET"])],
    )
    app.add_middleware(SlashNormalizationMiddleware)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app())


class TestSlashNormalizationMiddleware:
    def test_trailing_slash_stripped(self, client: TestClient) -> None:
        response = client.get("/items/")
        assert response.status_code == 200
        assert response.json() == {"path": "/items"}

    def test_no_trailing_slash_unchanged(self, client: TestClient) -> None:
        response = client.get("/items")
        assert response.status_code == 200
        assert response.json() == {"path": "/items"}

    def test_root_path_preserved(self, client: TestClient) -> None:
        """The root path ``/`` must not be stripped to an empty string."""
        response = client.get("/")
        # Root doesn't match /items, so 404 is expected — but path should stay "/"
        assert response.status_code == 404
