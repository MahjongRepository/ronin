import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from lobby.games.service import GamesService, RoomCreationError
from lobby.games.types import CreateRoomRequest
from lobby.registry.manager import RegistryManager
from lobby.server.settings import LobbyServerSettings
from lobby.views.handlers import create_room_and_redirect, create_templates, lobby_page
from shared.logging import setup_logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from starlette.requests import Request


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def list_servers(request: Request) -> JSONResponse:
    registry: RegistryManager = request.app.state.registry
    await registry.check_health()

    servers = registry.get_servers()
    return JSONResponse(
        {
            "servers": [
                {
                    "name": s.name,
                    "url": s.url,
                    "healthy": s.healthy,
                }
                for s in servers
            ],
        },
    )


async def list_rooms(request: Request) -> JSONResponse:
    games_service: GamesService = request.app.state.games_service
    rooms = await games_service.list_rooms()
    return JSONResponse({"rooms": rooms})


async def create_room(request: Request) -> JSONResponse:
    games_service: GamesService = request.app.state.games_service

    raw_body = await request.body()
    if not raw_body or raw_body.strip() == b"":
        body = {}
    else:
        try:
            body = json.loads(raw_body)
        except (ValueError, json.JSONDecodeError):  # fmt: skip
            return JSONResponse({"error": "Invalid JSON body"}, status_code=422)

    try:
        req = CreateRoomRequest(**body)
    except (TypeError, ValidationError) as e:
        return JSONResponse({"error": str(e)}, status_code=422)

    try:
        result = await games_service.create_room(num_ai_players=req.num_ai_players)
        return JSONResponse(
            {
                "room_id": result.room_id,
                "websocket_url": result.websocket_url,
                "server_name": result.server_name,
            },
            status_code=201,
        )
    except RoomCreationError as e:
        return JSONResponse({"error": str(e)}, status_code=503)


def create_app(settings: LobbyServerSettings | None = None) -> Starlette:
    if settings is None:  # pragma: no cover
        settings = LobbyServerSettings()

    static_dir = Path(settings.static_dir).resolve()

    routes = [
        Route("/", lobby_page, methods=["GET"]),
        Route("/rooms/new", create_room_and_redirect, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
        Route("/servers", list_servers, methods=["GET"]),
        Route("/rooms", list_rooms, methods=["GET"]),
        Route("/rooms", create_room, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=str(static_dir)), name="static"),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registry = RegistryManager(settings.config_path)
    app.state.settings = settings
    app.state.registry = registry
    app.state.templates = create_templates()
    games_service = GamesService(registry)
    app.state.games_service = games_service

    logger.info("lobby server ready")
    return app


settings = LobbyServerSettings()
setup_logging(log_dir=settings.log_dir)
app = create_app(settings=settings)
