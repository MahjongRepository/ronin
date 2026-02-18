from __future__ import annotations

import contextlib
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

from lobby.auth.middleware import AuthMiddleware
from lobby.games.service import GamesService, RoomCreationError
from lobby.games.types import CreateRoomRequest
from lobby.registry.manager import RegistryManager
from lobby.server.settings import LobbyServerSettings
from lobby.views.auth_handlers import bot_auth, bot_create_room, login, login_page, logout, register, register_page
from lobby.views.handlers import (
    create_room_and_redirect,
    create_templates,
    join_room_and_redirect,
    lobby_page,
)
from shared.auth import AuthService, AuthSessionStore, FileUserRepository
from shared.auth.settings import AuthSettings
from shared.logging import setup_logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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
    except RoomCreationError as e:
        return JSONResponse({"error": str(e)}, status_code=503)

    return JSONResponse(
        {
            "room_id": result.room_id,
            "websocket_url": result.websocket_url,
            "server_name": result.server_name,
        },
        status_code=201,
    )


def create_app(
    settings: LobbyServerSettings | None = None,
    auth_settings: AuthSettings | None = None,  # required in production (via get_app)
) -> Starlette:
    if settings is None:  # pragma: no cover
        settings = LobbyServerSettings()
    if auth_settings is None:  # pragma: no cover
        auth_settings = AuthSettings()  # type: ignore[call-arg]

    static_dir = Path(settings.static_dir).resolve()

    routes = [
        Route("/", lobby_page, methods=["GET"]),
        Route("/rooms/new", create_room_and_redirect, methods=["POST"]),
        Route("/rooms/{room_id}/join", join_room_and_redirect, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
        Route("/servers", list_servers, methods=["GET"]),
        Route("/rooms", list_rooms, methods=["GET"]),
        Route("/rooms", create_room, methods=["POST"]),
        Route("/login", login_page, methods=["GET"]),
        Route("/login", login, methods=["POST"]),
        Route("/register", register_page, methods=["GET"]),
        Route("/register", register, methods=["POST"]),
        Route("/logout", logout, methods=["POST"]),
        Route("/api/auth/bot", bot_auth, methods=["POST"]),
        Route("/api/rooms/create", bot_create_room, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=str(static_dir)), name="static"),
    ]

    # Initialize auth components
    user_repo = FileUserRepository(auth_settings.users_file)
    session_store = AuthSessionStore()
    auth_service = AuthService(user_repo, session_store)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:  # pragma: no cover
        session_store.start_cleanup()
        yield
        await session_store.stop_cleanup()

    app = Starlette(routes=routes, lifespan=lifespan)
    app.add_middleware(AuthMiddleware, auth_service=auth_service)  # type: ignore[arg-type]
    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registry = RegistryManager(settings.config_path)
    app.state.settings = settings
    app.state.auth_settings = auth_settings
    app.state.registry = registry
    app.state.templates = create_templates()
    games_service = GamesService(registry)
    app.state.games_service = games_service
    app.state.auth_service = auth_service

    logger.info("lobby server ready")
    return app


def get_app() -> Starlette:  # pragma: no cover  # deadcode: ignore
    """Factory function for uvicorn --factory lobby.server.app:get_app."""
    s = LobbyServerSettings()
    auth = AuthSettings()  # ty: ignore[missing-argument]
    setup_logging(log_dir=s.log_dir)
    return create_app(settings=s, auth_settings=auth)
