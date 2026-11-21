from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from starlette.responses import Response

from app.game_transition import (
    ObserveError,
    ReplayExportError,
    UnfinishedReplayError,
    fetch_observe,
    fetch_tenhou_replay,
)
from app.replay_storage import is_valid_game_id, read_replay

if TYPE_CHECKING:
    import httpx
    from starlette.requests import Request

    from app.settings import LobbyServerSettings

logger = structlog.get_logger()

_NOT_FOUND = Response("Not found", status_code=404, media_type="text/plain")

_TENHOU_CACHE_SECONDS = 3600

_NO_STORE = {"Cache-Control": "no-store"}


async def replay_content(request: Request) -> Response:
    """
    GET /api/replays/{game_id} — serve a gzip-compressed replay file.
    """
    game_id = request.path_params["game_id"]
    replay_dir_str: str = request.app.state.settings.replay_dir
    gzip_bytes = await asyncio.to_thread(read_replay, replay_dir_str, game_id)
    if gzip_bytes is None:
        return _NOT_FOUND

    return Response(
        content=gzip_bytes,
        media_type="application/msgpack",
        headers={
            "Content-Encoding": "gzip",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


async def tenhou_replay(request: Request) -> Response:
    """
    GET /api/replays/{game_id}/tenhou.xml — download a replay as a tenhou.net XML log, converted by the game server.

    The answer is cached for a limited time only, since a converter fix changes it.
    """
    game_id = request.path_params["game_id"]
    if not is_valid_game_id(game_id):
        return _NOT_FOUND

    settings: LobbyServerSettings = request.app.state.settings
    game_server: httpx.AsyncClient = request.app.state.game_server
    try:
        xml = await fetch_tenhou_replay(game_id, settings=settings, game_server=game_server)
    except UnfinishedReplayError:
        return Response("Tenhou export needs a finished game", status_code=422, media_type="text/plain")
    except ReplayExportError as e:
        logger.warning("tenhou replay export failed", game_id=game_id, error=str(e))
        return Response("Tenhou export failed", status_code=502, media_type="text/plain")

    if xml is None:
        return _NOT_FOUND

    return Response(
        content=xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{game_id}.xml"',
            "Cache-Control": f"public, max-age={_TENHOU_CACHE_SECONDS}",
        },
    )


async def observe_stream(request: Request) -> Response:
    """
    GET /api/observe/{game_id}?from=N — pass through the game server's delayed observer records of a live game.

    404 means the game server observes no such game (never started, or ended past its delay), 503 that it could not be
    asked. Every answer is ``no-store``, since the stream grows while the game plays.
    """
    game_id = request.path_params["game_id"]
    if not is_valid_game_id(game_id):
        return Response("Not found", status_code=404, media_type="text/plain", headers=_NO_STORE)

    raw_from = request.query_params.get("from", "0")
    if not (raw_from.isascii() and raw_from.isdigit()):
        return Response("Bad from", status_code=400, media_type="text/plain", headers=_NO_STORE)

    settings: LobbyServerSettings = request.app.state.settings
    game_server: httpx.AsyncClient = request.app.state.game_server
    try:
        body = await fetch_observe(game_id, int(raw_from), settings=settings, game_server=game_server)
    except ObserveError as e:
        logger.warning("observe stream fetch failed", game_id=game_id, error=str(e))
        return Response("Observe unavailable", status_code=503, media_type="text/plain", headers=_NO_STORE)

    if body is None:
        return Response("Not found", status_code=404, media_type="text/plain", headers=_NO_STORE)

    return Response(content=body, media_type="application/msgpack", headers=_NO_STORE)
