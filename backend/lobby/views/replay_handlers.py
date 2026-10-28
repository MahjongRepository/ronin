from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from starlette.responses import Response

from lobby.game_transition import ReplayExportError, UnfinishedReplayError, fetch_tenhou_replay
from shared.storage import is_valid_game_id, read_replay

if TYPE_CHECKING:
    import httpx
    from starlette.requests import Request

    from lobby.settings import LobbyServerSettings

logger = structlog.get_logger()

_NOT_FOUND = Response("Not found", status_code=404, media_type="text/plain")

_TENHOU_CACHE_SECONDS = 3600


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
        media_type="application/x-ndjson",
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
