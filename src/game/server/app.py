import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute

from game.logic.mahjong_service import MahjongGameService
from game.messaging.router import MessageRouter
from game.server.settings import GameServerSettings
from game.server.types import CreateGameRequest
from game.server.websocket import websocket_endpoint
from game.session.manager import SessionManager
from game.session.replay_collector import ReplayCollector
from shared.logging import setup_logging
from shared.storage import LocalReplayStorage

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.websockets import WebSocket

    from game.logic.service import GameService


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def status(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    settings: GameServerSettings = request.app.state.settings
    return JSONResponse(
        {
            "status": "ok",
            "active_games": session_manager.game_count,
            "max_games": settings.max_games,
        }
    )


async def list_games(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    games = session_manager.get_games_info()
    return JSONResponse({"games": [g.model_dump() for g in games]})


async def create_game(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    settings: GameServerSettings = request.app.state.settings

    try:
        body = await request.json()
        game_request = CreateGameRequest(**body)
    except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if session_manager.game_count >= settings.max_games:
        return JSONResponse({"error": "Server at capacity"}, status_code=503)

    if session_manager.get_game(game_request.game_id):
        return JSONResponse({"error": "Game already exists"}, status_code=409)

    session_manager.create_game(game_request.game_id, num_bots=game_request.num_bots)
    return JSONResponse(
        {"game_id": game_request.game_id, "num_bots": game_request.num_bots, "status": "created"},
        status_code=201,
    )


def create_app(
    settings: GameServerSettings | None = None,
    game_service: GameService | None = None,
    session_manager: SessionManager | None = None,
    message_router: MessageRouter | None = None,
) -> Starlette:
    if settings is None:
        settings = GameServerSettings()

    if game_service is None:
        game_service = MahjongGameService()

    if session_manager is None:
        storage = LocalReplayStorage(settings.replay_dir)
        replay_collector = ReplayCollector(storage)
        session_manager = SessionManager(
            game_service, log_dir=settings.log_dir, replay_collector=replay_collector
        )

    if message_router is None:
        message_router = MessageRouter(session_manager)

    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket_endpoint(websocket, message_router)

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/status", status, methods=["GET"]),
        Route("/games", list_games, methods=["GET"]),
        Route("/games", create_game, methods=["POST"]),
        WebSocketRoute("/ws/{game_id}", ws_endpoint),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.session_manager = session_manager

    logger.info("game server ready")
    return app


settings = GameServerSettings()
setup_logging(log_dir=settings.log_dir)
app = create_app(settings=settings)
