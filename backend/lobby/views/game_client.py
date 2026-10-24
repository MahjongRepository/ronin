from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import httpx
import structlog
from starlette.responses import FileResponse, PlainTextResponse, Response

if TYPE_CHECKING:
    from pathlib import Path

    from starlette.requests import Request

logger = structlog.get_logger()

GAME_ASSETS_PATH = "/game-assets"
_DEV_SERVER_TIMEOUT_SECONDS = 30.0
_FORWARDED_RESPONSE_HEADERS = ("content-type", "cache-control", "etag")


class GameClient(Protocol):
    async def serve_page(self) -> Response: ...


@dataclass(frozen=True)
class BuiltGameClient:
    """
    Serve the game client's production build: its ``index.html`` answers every game page.
    """

    directory: Path

    async def serve_page(self) -> Response:
        index = self.directory / "index.html"
        if not index.is_file():
            return PlainTextResponse("Game client assets not available", status_code=503)

        return FileResponse(index, media_type="text/html")


@dataclass(frozen=True)
class DevGameClient:
    """
    Proxy the game client's page and files to its Vite dev server, keeping them on the lobby's origin.

    The lobby hands a game over through ``sessionStorage``, which only a page on the same origin can read.
    """

    origin: str
    transport: httpx.AsyncBaseTransport | None = None

    async def serve_page(self) -> Response:
        return await self._forward(f"{GAME_ASSETS_PATH}/", accept="text/html")

    async def serve_asset(self, request: Request) -> Response:
        path = request.scope["raw_path"].decode("ascii")
        query = request.scope["query_string"].decode("ascii")
        if query:
            path = f"{path}?{query}"

        return await self._forward(path, accept=request.headers.get("accept", "*/*"))

    async def _forward(self, path: str, *, accept: str) -> Response:
        async with httpx.AsyncClient(
            base_url=self.origin,
            transport=self.transport,
            timeout=_DEV_SERVER_TIMEOUT_SECONDS,
        ) as client:
            try:
                upstream = await client.get(path, headers={"accept": accept})
            except httpx.HTTPError:
                logger.exception("game client dev server unreachable", origin=self.origin, path=path)
                return PlainTextResponse("Game client dev server not reachable", status_code=502)

        headers = {name: upstream.headers[name] for name in _FORWARDED_RESPONSE_HEADERS if name in upstream.headers}
        return Response(upstream.content, status_code=upstream.status_code, headers=headers)
