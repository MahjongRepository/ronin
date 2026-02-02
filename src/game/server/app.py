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
from game.server.types import CreateGameRequest
from game.server.websocket import websocket_endpoint
from game.session.manager import SessionManager
from shared.logging import setup_logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.websockets import WebSocket

    from game.logic.service import GameService


MAX_GAMES = 100
GAME_LOG_DIR = "logs/game"


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def status(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    return JSONResponse(
        {
            "status": "ok",
            "active_games": session_manager.game_count,
            "max_games": MAX_GAMES,
        }
    )


async def list_games(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    games = session_manager.get_games_info()
    return JSONResponse({"games": [g.model_dump() for g in games]})


async def create_game(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager

    try:
        body = await request.json()
        game_request = CreateGameRequest(**body)
    except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    if session_manager.game_count >= MAX_GAMES:
        return JSONResponse({"error": "Server at capacity"}, status_code=503)

    if session_manager.get_game(game_request.game_id):
        return JSONResponse({"error": "Game already exists"}, status_code=409)

    session_manager.create_game(game_request.game_id, num_bots=game_request.num_bots)
    return JSONResponse(
        {"game_id": game_request.game_id, "num_bots": game_request.num_bots, "status": "created"},
        status_code=201,
    )


def create_app(
    game_service: GameService | None = None,
    session_manager: SessionManager | None = None,
    message_router: MessageRouter | None = None,
) -> Starlette:
    if game_service is None:
        game_service = MahjongGameService()

    if session_manager is None:
        session_manager = SessionManager(game_service, log_dir=GAME_LOG_DIR)

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
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.session_manager = session_manager

    logger.info("game server ready")
    return app


setup_logging(log_dir=GAME_LOG_DIR)
app = create_app()
