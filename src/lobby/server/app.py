from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from lobby.games.service import GameCreationError, GamesService
from lobby.registry.manager import RegistryManager

if TYPE_CHECKING:
    from pathlib import Path

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


async def create_game(request: Request) -> JSONResponse:
    games_service: GamesService = request.app.state.games_service

    try:
        result = await games_service.create_game()

        return JSONResponse(
            {
                "room_id": result.room_id,
                "websocket_url": result.websocket_url,
                "server_name": result.server_name,
            },
            status_code=201,
        )
    except GameCreationError as e:
        return JSONResponse({"error": str(e)}, status_code=503)


def create_app(config_path: Path | None = None) -> Starlette:
    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/servers", list_servers, methods=["GET"]),
        Route("/games", create_game, methods=["POST"]),
    ]

    app = Starlette(routes=routes)

    registry = RegistryManager(config_path)
    app.state.registry = registry
    app.state.games_service = GamesService(registry)

    return app


app = create_app()
