import asyncio
import contextlib
import gzip
import hmac
import json
from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, WebSocketRoute

from game.logic.mahjong_service import MahjongGameService
from game.replay.external.tenhou import IncompleteReplayError, convert_replay_content
from game.server.router import MessageRouter
from game.server.settings import GameServerSettings
from game.server.types import CreateGameRequest
from game.server.websocket import websocket_endpoint
from game.session.manager import SessionManager
from game.session.replay_collector import ReplayCollector
from shared.auth.game_ticket import verify_game_ticket
from shared.build_info import APP_VERSION, GIT_COMMIT
from shared.db import Database, SqliteGameRepository
from shared.logging import setup_logging
from shared.storage import LocalReplayStorage, read_replay

logger = structlog.get_logger()

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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


async def player_game(request: Request) -> JSONResponse:
    """
    Answer 200 with the id of the game a user is playing, or 404 (internal: the lobby's occupancy check).
    """
    session_manager: SessionManager = request.app.state.session_manager
    game_id = session_manager.get_playing_game_id(request.path_params["user_id"])
    if game_id is None:
        return JSONResponse({"error": "Player is not in a game"}, status_code=404)

    return JSONResponse({"game_id": game_id})


_NO_STORE = {"Cache-Control": "no-store"}
_BEARER_PREFIX = "Bearer "


def _is_internal_caller(request: Request, secret: str) -> bool:
    """
    Check the request carries the internal API secret as its bearer token.
    """
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith(_BEARER_PREFIX):
        return False

    return hmac.compare_digest(authorization.removeprefix(_BEARER_PREFIX).encode(), secret.encode())


async def player_game_session(request: Request) -> JSONResponse:
    """
    Answer 200 with the game a user is playing and their participant's exact ticket, or 404 (internal, credential
    bearing: the lobby's recovery of a lost game handoff).

    The ticket is the very string the participant is keyed by, so it joins a pending game and reconnects to a playing
    one. Only a caller with the internal API secret gets an answer, never a browser, and no answer is cached.
    """
    settings: GameServerSettings = request.app.state.settings
    if not _is_internal_caller(request, settings.internal_api_secret):
        return JSONResponse({"error": "Unauthorized"}, status_code=401, headers=_NO_STORE)

    session_manager: SessionManager = request.app.state.session_manager
    participant = session_manager.get_playing_participant(request.path_params["user_id"])
    if participant is None:
        return JSONResponse({"error": "Player is not in a game"}, status_code=404, headers=_NO_STORE)

    return JSONResponse({"game_id": participant.game.game_id, "game_ticket": participant.ticket}, headers=_NO_STORE)


def _export_tenhou_replay(replay_dir: str, game_id: str) -> str | None:
    gzip_bytes = read_replay(replay_dir, game_id)
    if gzip_bytes is None:
        return None

    return convert_replay_content(gzip.decompress(gzip_bytes).decode())


async def tenhou_replay(request: Request) -> Response:
    """
    Answer 200 with a stored replay converted to tenhou.net XML, 404 when none is stored, or 422 for a failed game's
    replay, which has no game end (internal: the lobby's public Tenhou download).

    Only a caller with the internal API secret gets an answer, so the conversion runs only behind the lobby's route and
    its rate limit; it runs in a worker thread to keep the event loop serving games.
    """
    settings: GameServerSettings = request.app.state.settings
    if not _is_internal_caller(request, settings.internal_api_secret):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    try:
        xml = await asyncio.to_thread(_export_tenhou_replay, settings.replay_dir, request.path_params["game_id"])
    except IncompleteReplayError:
        return JSONResponse({"error": "Replay has no game end"}, status_code=422)

    if xml is None:
        return JSONResponse({"error": "Replay not found"}, status_code=404)

    return Response(xml, media_type="application/xml")


_MAX_REQUEST_BODY_SIZE = 4096


def _validate_player_tickets(game_request: CreateGameRequest, secret: str) -> str | None:
    """
    Verify each player's ticket signature, expiry, and identity claims.

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


def _reject_game_request(
    game_request: CreateGameRequest,
    *,
    session_manager: SessionManager,
    settings: GameServerSettings,
) -> JSONResponse | None:
    """
    Return the error response for a game that must not be created, or None.

    A player already playing a game here (pending included) is refused with 409: the lobby's occupancy check runs before
    the game is created, and this is its backstop.
    """
    ticket_error = _validate_player_tickets(game_request, settings.game_ticket_secret)
    if ticket_error is not None:
        return JSONResponse({"error": ticket_error}, status_code=400)

    if any(session_manager.get_playing_game_id(player.user_id) is not None for player in game_request.players):
        return JSONResponse({"error": "Player already in a game"}, status_code=409)

    if session_manager.game_count >= settings.max_capacity:
        return JSONResponse({"error": "Server at capacity"}, status_code=503)

    return None


async def _read_request_body(request: Request) -> bytes | JSONResponse:
    """
    Stream-read request body with hard size cutoff.

    Returns raw bytes on success, or a JSONResponse error on failure.
    """
    chunks: list[bytes] = []
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > _MAX_REQUEST_BODY_SIZE:
                return JSONResponse({"error": "Request body too large"}, status_code=413)

            chunks.append(chunk)
    except ClientDisconnect:
        return JSONResponse({"error": "Client disconnected"}, status_code=400)

    return b"".join(chunks)


async def create_game(request: Request) -> JSONResponse:
    session_manager: SessionManager = request.app.state.session_manager
    settings: GameServerSettings = request.app.state.settings

    try:
        result = await _read_request_body(request)
        if isinstance(result, JSONResponse):
            return result

        raw_body = result
        body = json.loads(raw_body)
        game_request = CreateGameRequest(**body)
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError, ValidationError):  # fmt: skip
        return JSONResponse({"error": "Invalid request body"}, status_code=400)

    rejection = _reject_game_request(game_request, session_manager=session_manager, settings=settings)
    if rejection is not None:
        return rejection

    try:
        session_manager.create_pending_game(
            game_id=game_request.game_id,
            player_specs=game_request.players,
        )
    except ValueError:
        return JSONResponse({"error": "Game with this ID already exists"}, status_code=409)

    return JSONResponse(
        {"game_id": game_request.game_id, "status": "pending"},
        status_code=201,
    )


async def withdraw_game(request: Request) -> Response:
    """
    Answer 204 once a game the lobby gave up on is withdrawn, or 409 when a player already joined it (internal: the
    lobby's cleanup after a start whose outcome it never learned).
    """
    settings: GameServerSettings = request.app.state.settings
    if not _is_internal_caller(request, settings.internal_api_secret):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    session_manager: SessionManager = request.app.state.session_manager
    if not session_manager.withdraw_game(request.path_params["game_id"]):
        return JSONResponse({"error": "Game already joined"}, status_code=409)

    return Response(status_code=204)


def create_app(
    settings: GameServerSettings | None = None,
    game_service: GameService | None = None,
    session_manager: SessionManager | None = None,
    message_router: MessageRouter | None = None,
) -> Starlette:
    if settings is None:
        settings = GameServerSettings()

    if game_service is None:  # pragma: no cover (entrypoint)
        game_service = MahjongGameService()

    # When the app creates its own SessionManager, it owns the DB lifecycle.
    owned_db: Database | None = None

    if session_manager is None:
        db = Database(settings.database_path)
        owned_db = db
        game_repository = SqliteGameRepository(db)

        storage = LocalReplayStorage(settings.replay_dir)
        replay_collector = ReplayCollector(storage)
        session_manager = SessionManager(
            game_service,
            game_repository=game_repository,
            replay_collector=replay_collector,
        )

    if message_router is None:
        message_router = MessageRouter(session_manager, game_ticket_secret=settings.game_ticket_secret)

    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket_endpoint(websocket, message_router)

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/status", status, methods=["GET"]),
        Route("/games", create_game, methods=["POST"]),
        Route("/games/{game_id}", withdraw_game, methods=["DELETE"]),
        Route("/players/{user_id}", player_game, methods=["GET"]),
        Route("/players/{user_id}/game-session", player_game_session, methods=["GET"]),
        Route("/replays/{game_id}/tenhou", tenhou_replay, methods=["GET"]),
        WebSocketRoute("/ws/{game_id}", ws_endpoint),
    ]

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
        try:
            if owned_db is not None:
                await owned_db.open()

            yield
        finally:
            try:
                await session_manager.shutdown()
            finally:
                if owned_db is not None:
                    await owned_db.close()

    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.settings = settings
    app.state.session_manager = session_manager

    logger.info("game server ready")
    return app


def get_app() -> Starlette:  # pragma: no cover (entrypoint)  # deadcode: ignore
    """
    ASGI application factory for production use (e.g., uvicorn --factory).
    """
    _settings = GameServerSettings()
    setup_logging(log_dir=_settings.log_dir)
    return create_app(settings=_settings)
