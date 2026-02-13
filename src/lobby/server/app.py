import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route

from lobby.games.service import GamesService, RoomCreationError
from lobby.games.types import CreateRoomRequest
from lobby.registry.manager import RegistryManager
from lobby.server.settings import LobbyServerSettings
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
            ]
        }
    )


async def list_rooms(request: Request) -> JSONResponse:
    games_service: GamesService = request.app.state.games_service
    rooms = await games_service.list_rooms()
    return JSONResponse({"rooms": rooms})


async def create_room(request: Request) -> JSONResponse:
    games_service: GamesService = request.app.state.games_service

    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        body = {}

    try:
        req = CreateRoomRequest(**body)
    except (TypeError, ValidationError) as e:
        return JSONResponse({"error": str(e)}, status_code=422)

    try:
        result = await games_service.create_room(num_bots=req.num_bots)
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
    if settings is None:
        settings = LobbyServerSettings()

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/servers", list_servers, methods=["GET"]),
        Route("/rooms", list_rooms, methods=["GET"]),
        Route("/rooms", create_room, methods=["POST"]),
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
    games_service = GamesService(registry)
    app.state.games_service = games_service

    logger.info("lobby server ready")
    return app


settings = LobbyServerSettings()
setup_logging(log_dir=settings.log_dir)
app = create_app(settings=settings)
