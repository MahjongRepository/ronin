import json
from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute

from game.logic.mahjong_service import MahjongGameService
from game.messaging.router import MessageRouter
from game.server.settings import GameServerSettings
from game.server.types import CreateRoomRequest
from game.server.websocket import websocket_endpoint
from game.session.manager import SessionManager
from game.session.replay_collector import ReplayCollector
from shared.build_info import APP_VERSION, GIT_COMMIT
from shared.db import Database, SqliteGameRepository
from shared.logging import setup_logging
from shared.storage import LocalReplayStorage

logger = structlog.get_logger()

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.websockets import WebSocket

    from game.logic.service import GameService


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "version": APP_VERSION, "commit": GIT_COMMIT})


async def status(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    settings: GameServerSettings = request.app.state.settings
    return JSONResponse(
        {
            "status": "ok",
            "version": APP_VERSION,
            "commit": GIT_COMMIT,
            "active_rooms": session_manager.room_count,
            "active_games": session_manager.game_count,
            "capacity_used": session_manager.room_count + session_manager.game_count,
            "max_capacity": settings.max_capacity,
        },
    )


async def list_rooms(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    rooms = session_manager.get_rooms_info()
    return JSONResponse({"rooms": [r.model_dump() for r in rooms]})


_MAX_REQUEST_BODY_SIZE = 4096


async def create_room(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    settings: GameServerSettings = request.app.state.settings

    try:
        raw_body = await request.body()
        if len(raw_body) > _MAX_REQUEST_BODY_SIZE:
            return JSONResponse({"error": "Request body too large"}, status_code=413)
        body = json.loads(raw_body)
        room_request = CreateRoomRequest(**body)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError, ValidationError):  # fmt: skip
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    if session_manager.room_count + session_manager.game_count >= settings.max_capacity:
        return JSONResponse({"error": "Server at capacity"}, status_code=503)

    if session_manager.get_room(room_request.room_id) is not None:
        return JSONResponse({"error": "Room already exists"}, status_code=409)

    if session_manager.get_game(room_request.room_id) is not None:
        return JSONResponse({"error": "Game with this ID already exists"}, status_code=409)

    session_manager.create_room(room_request.room_id, num_ai_players=room_request.num_ai_players)
    return JSONResponse(
        {"room_id": room_request.room_id, "num_ai_players": room_request.num_ai_players, "status": "created"},
        status_code=201,
    )


def create_app(
    settings: GameServerSettings | None = None,
    game_service: GameService | None = None,
    session_manager: SessionManager | None = None,
    message_router: MessageRouter | None = None,
) -> Starlette:
    if settings is None:  # pragma: no cover
        settings = GameServerSettings()  # ty: ignore[missing-argument]

    if game_service is None:  # pragma: no cover
        game_service = MahjongGameService()

    # When the app creates its own SessionManager, it owns the DB lifecycle.
    owned_db: Database | None = None

    if session_manager is None:
        db = Database(settings.database_path)
        db.connect()
        owned_db = db
        game_repository = SqliteGameRepository(db)

        storage = LocalReplayStorage(settings.replay_dir)
        replay_collector = ReplayCollector(storage)
        session_manager = SessionManager(
            game_service,
            log_dir=settings.log_dir,
            replay_collector=replay_collector,
            room_ttl_seconds=settings.room_ttl_seconds,
            game_repository=game_repository,
        )

    if message_router is None:
        message_router = MessageRouter(session_manager, game_ticket_secret=settings.game_ticket_secret)

    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket_endpoint(websocket, message_router)

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/status", status, methods=["GET"]),
        Route("/rooms", list_rooms, methods=["GET"]),
        Route("/rooms", create_room, methods=["POST"]),
        WebSocketRoute("/ws/{room_id}", ws_endpoint),
    ]

    async def on_startup() -> None:
        session_manager.start_room_reaper()

    async def on_shutdown() -> None:
        await session_manager.stop_room_reaper()
        if owned_db is not None:
            owned_db.close()

    app = Starlette(routes=routes, on_startup=[on_startup], on_shutdown=[on_shutdown])
    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.settings = settings
    app.state.session_manager = session_manager

    logger.info("game server ready")
    return app


def get_app() -> Starlette:  # pragma: no cover  # deadcode: ignore
    """ASGI application factory for production use (e.g., uvicorn --factory)."""
    _settings = GameServerSettings()  # ty: ignore[missing-argument]
    setup_logging()
    return create_app(settings=_settings)
