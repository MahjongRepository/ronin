import logging
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from lobby.games.service import GameCreationError, GamesService
from lobby.registry.manager import RegistryManager
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


async def list_games(request: Request) -> JSONResponse:
    games_service: GamesService = request.app.state.games_service
    games = await games_service.list_games()
    return JSONResponse({"games": games})


async def create_game(request: Request) -> JSONResponse:
    games_service: GamesService = request.app.state.games_service

    try:
        result = await games_service.create_game()

        return JSONResponse(
            {
                "game_id": result.game_id,
                "websocket_url": result.websocket_url,
                "server_name": result.server_name,
            },
            status_code=201,
        )
    except GameCreationError as e:
        return JSONResponse({"error": str(e)}, status_code=503)


async def redirect_to_index(_request: Request) -> RedirectResponse:
    """
    Redirect root path to the static index page.
    """
    return RedirectResponse(url="/static/index.html")


def create_app(config_path: Path | None = None) -> Starlette:
    # path to static files directory
    static_dir = Path(__file__).parent.parent / "static"

    routes = [
        Route("/", redirect_to_index, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/servers", list_servers, methods=["GET"]),
        Route("/games", list_games, methods=["GET"]),
        Route("/games", create_game, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=static_dir), name="static"),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registry = RegistryManager(config_path)
    app.state.registry = registry
    app.state.games_service = GamesService(registry)

    logger.info("lobby server ready")
    return app


setup_logging(log_dir="logs/lobby")
app = create_app()
