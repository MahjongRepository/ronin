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
from game.server.types import CreateGameRequest
from game.server.websocket import websocket_endpoint
from game.session.manager import SessionManager
from game.session.replay_collector import ReplayCollector
from shared.auth.game_ticket import verify_game_ticket
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
            "pending_games": session_manager.pending_game_count,
            "active_games": session_manager.started_game_count,
            "capacity_used": session_manager.game_count,
            "max_capacity": settings.max_capacity,
        },
    )


_MAX_REQUEST_BODY_SIZE = 4096


def _validate_player_tickets(game_request: CreateGameRequest, secret: str) -> str | None:
    """Verify each player's ticket signature, expiry, and identity claims.

    Returns an error message string if validation fails, or None if all tickets are valid.
    """
    for player_spec in game_request.players:
        ticket = verify_game_ticket(player_spec.game_ticket, secret)
        if ticket is None:
            return "Invalid or expired game ticket"
        if ticket.room_id != game_request.game_id:
            return "Ticket game_id mismatch"
        if ticket.username != player_spec.name or ticket.user_id != player_spec.user_id:
            return "Ticket identity mismatch"
    return None


async def create_game(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    settings: GameServerSettings = request.app.state.settings

    try:
        raw_body = await request.body()
        if len(raw_body) > _MAX_REQUEST_BODY_SIZE:
            return JSONResponse({"error": "Request body too large"}, status_code=413)
        body = json.loads(raw_body)
        game_request = CreateGameRequest(**body)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError, ValidationError):  # fmt: skip
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    ticket_error = _validate_player_tickets(game_request, settings.game_ticket_secret)
    if ticket_error is not None:
        return JSONResponse({"error": ticket_error}, status_code=400)

    if session_manager.game_count >= settings.max_capacity:
        return JSONResponse({"error": "Server at capacity"}, status_code=503)

    try:
        session_manager.create_pending_game(
            game_request.game_id,
            game_request.players,
            game_request.num_ai_players,
        )
    except ValueError:
        return JSONResponse({"error": "Game with this ID already exists"}, status_code=409)

    return JSONResponse(
        {"game_id": game_request.game_id, "status": "pending"},
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
            game_repository=game_repository,
        )

    if message_router is None:
        message_router = MessageRouter(session_manager, game_ticket_secret=settings.game_ticket_secret)

    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket_endpoint(websocket, message_router)

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/status", status, methods=["GET"]),
        Route("/games", create_game, methods=["POST"]),
        WebSocketRoute("/ws/{game_id}", ws_endpoint),
    ]

    async def on_shutdown() -> None:
        session_manager.cancel_all_pending_timeouts()
        if owned_db is not None:
            owned_db.close()

    app = Starlette(routes=routes, on_shutdown=[on_shutdown])
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
