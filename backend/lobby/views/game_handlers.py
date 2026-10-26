from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from typing import TYPE_CHECKING

import structlog
from starlette.responses import JSONResponse

from lobby.game_transition import GameLookupError, find_game_handoff
from lobby.views.assets import render_page

if TYPE_CHECKING:
    import httpx
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.settings import LobbyServerSettings
    from lobby.views.game_client import GameClient

logger = structlog.get_logger()

_NO_STORE = {"Cache-Control": "no-store"}


async def play_page(request: Request) -> Response:
    """
    GET /play/* — serve the game client's page; the game client routes the path itself.
    """
    game_client: GameClient = request.app.state.game_client
    return await game_client.serve_page()


async def game_session(request: Request) -> JSONResponse:
    """
    GET /api/game-session — recover the handoff of the game the authenticated user is playing (the game page's missing
    session).

    The user comes only from the request's authentication, never from the client. 404 means no live game, 503 that the
    game server could not be asked; the credential-bearing answer is never cached.
    """
    settings: LobbyServerSettings = request.app.state.settings
    game_server: httpx.AsyncClient = request.app.state.game_server
    try:
        handoff = await find_game_handoff(request.user.user_id, settings=settings, game_server=game_server)
    except GameLookupError as e:
        logger.warning("game handoff lookup failed", username=request.user.username, error=str(e))
        return JSONResponse(
            {"error": "game_lookup_failed"}, status_code=HTTPStatus.SERVICE_UNAVAILABLE, headers=_NO_STORE
        )

    if handoff is None:
        return JSONResponse({"error": "not_playing"}, status_code=HTTPStatus.NOT_FOUND, headers=_NO_STORE)

    return JSONResponse(asdict(handoff), headers=_NO_STORE)


async def storybook_page(request: Request) -> Response:
    """
    Render the lobby storybook page for development.
    """
    username = request.user.username if request.user.is_authenticated else None
    return render_page(request, template_name="storybook.html", context={"username": username})
