from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from lobby.auth.backend import SessionOrApiKeyBackend
from lobby.auth.policy import (
    bot_only,
    collect_protected_api_paths,
    protected_api,
    protected_html,
    public_route,
    validate_route_auth_policy,
)
from lobby.registry.manager import RegistryManager
from lobby.rooms.connections import RoomConnectionManager
from lobby.rooms.manager import LobbyRoomManager
from lobby.rooms.websocket import room_websocket
from lobby.server.middleware import SecurityHeadersMiddleware, SlashNormalizationMiddleware
from lobby.server.settings import LobbyServerSettings
from lobby.views.auth_handlers import bot_auth, bot_create_room, login, login_page, logout, register, register_page
from lobby.views.handlers import (
    create_room_and_redirect,
    create_templates,
    game_page,
    game_styleguide_page,
    join_room_and_redirect,
    load_vite_manifest,
    lobby_page,
    resolve_vite_asset_urls,
    room_page,
    styleguide_page,
)
from shared.auth import AuthService, AuthSessionStore
from shared.auth.password import get_hasher
from shared.auth.settings import AuthSettings
from shared.build_info import APP_VERSION, GIT_COMMIT
from shared.db import Database, SqlitePlayerRepository
from shared.logging import setup_logging

logger = structlog.get_logger()

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from starlette.requests import Request


def _make_auth_error_handler(
    protected_api_paths: set[str],
) -> Callable[[Request, Exception], Awaitable[Response]]:
    """Build an HTTPException handler that rewrites 401s on protected JSON endpoints."""

    async def _auth_error_handler(request: Request, exc: Exception) -> Response:
        """Rewrite 401 errors on protected JSON endpoints to JSON responses.

        All other HTTP exceptions delegate to Starlette's default behavior
        (plain-text response with the exception detail).
        """
        http_exc = cast("HTTPException", exc)
        if http_exc.status_code == HTTPStatus.UNAUTHORIZED and request.url.path in protected_api_paths:
            return JSONResponse({"error": "Authentication required"}, status_code=HTTPStatus.UNAUTHORIZED)
        if http_exc.status_code in {HTTPStatus.NO_CONTENT, HTTPStatus.NOT_MODIFIED}:
            return Response(status_code=http_exc.status_code, headers=http_exc.headers)
        return PlainTextResponse(http_exc.detail or "", status_code=http_exc.status_code, headers=http_exc.headers)

    return _auth_error_handler


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "version": APP_VERSION, "commit": GIT_COMMIT})


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


def create_app(
    settings: LobbyServerSettings | None = None,
    auth_settings: AuthSettings | None = None,  # required in production (via get_app)
) -> Starlette:
    if settings is None:  # pragma: no cover
        settings = LobbyServerSettings()
    if auth_settings is None:  # pragma: no cover
        auth_settings = AuthSettings()  # type: ignore[call-arg]

    static_dir = Path(settings.static_dir).resolve()
    game_assets_dir = Path(settings.game_assets_dir).resolve()

    room_connections = RoomConnectionManager()
    room_manager = LobbyRoomManager(
        room_ttl_seconds=300,
        on_room_expired=lambda room_id, _conn_ids: room_connections.close_connections(
            room_id,
            code=4002,
            reason="room_expired",
        ),
    )

    routes = [
        # Protected HTML routes (redirect to login when unauthenticated)
        Route("/", protected_html(lobby_page), methods=["GET"], name="lobby_page"),
        Route("/game", protected_html(game_page), methods=["GET"], name="game_page"),
        Route(
            "/rooms/new",
            protected_html(create_room_and_redirect),
            methods=["POST"],
            name="create_room_and_redirect",
        ),
        Route(
            "/rooms/{room_id}",
            protected_html(room_page),
            methods=["GET"],
            name="room_page",
        ),
        Route(
            "/rooms/{room_id}/join",
            protected_html(join_room_and_redirect),
            methods=["POST"],
            name="join_room_and_redirect",
        ),
        # Protected JSON routes (return 401 JSON when unauthenticated)
        Route("/servers", protected_api(list_servers), methods=["GET"], name="list_servers"),
        # WebSocket route (auth handled inside the handler)
        WebSocketRoute("/ws/rooms/{room_id}", room_websocket, name="room_websocket"),
        # Public routes
        Route("/health", public_route(health), methods=["GET"], name="health"),
        Route("/login", public_route(login_page), methods=["GET"], name="login_page"),
        Route("/login", public_route(login), methods=["POST"], name="login"),
        Route("/register", public_route(register_page), methods=["GET"], name="register_page"),
        Route("/register", public_route(register), methods=["POST"], name="register"),
        Route("/logout", public_route(logout), methods=["POST"], name="logout"),
        Route("/api/auth/bot", bot_only(bot_auth), methods=["POST"], name="bot_auth"),
        Route("/api/rooms", bot_only(bot_create_room), methods=["POST"], name="bot_create_room"),
    ]

    if APP_VERSION == "dev":
        routes.extend(
            [
                Route("/styleguide", public_route(styleguide_page), methods=["GET"], name="styleguide_page"),
                Route(
                    "/game/styleguide",
                    public_route(game_styleguide_page),
                    methods=["GET"],
                    name="game_styleguide_page",
                ),
            ],
        )

    if static_dir.is_dir():
        routes.append(Mount("/static", app=StaticFiles(directory=str(static_dir)), name="static"))

    if game_assets_dir.is_dir():
        routes.append(
            Mount("/game-assets", app=StaticFiles(directory=str(game_assets_dir)), name="game_assets"),
        )
    else:
        logger.warning("game assets directory not found, /game-assets/ will not be served", path=str(game_assets_dir))

    validate_route_auth_policy(routes)
    protected_api_paths = collect_protected_api_paths(routes)

    # Initialize database and auth components
    db = Database(auth_settings.database_path)
    db.connect()
    player_repo = SqlitePlayerRepository(db)
    session_store = AuthSessionStore()
    hasher = get_hasher(auth_settings.password_hasher)
    auth_service = AuthService(player_repo, session_store, password_hasher=hasher)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:  # pragma: no cover
        session_store.start_cleanup()
        room_manager.start_reaper()
        yield
        await room_manager.stop_reaper()
        await session_store.stop_cleanup()
        db.close()

    app = Starlette(
        routes=routes,
        lifespan=lifespan,
        exception_handlers={HTTPException: _make_auth_error_handler(protected_api_paths)},
    )
    app.add_middleware(SlashNormalizationMiddleware)  # type: ignore[arg-type]
    app.add_middleware(AuthenticationMiddleware, backend=SessionOrApiKeyBackend(auth_service))  # type: ignore[arg-type]
    app.add_middleware(
        CORSMiddleware,  # type: ignore[arg-type]
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    app.add_middleware(SecurityHeadersMiddleware, vite_dev_url=settings.vite_dev_url)  # type: ignore[arg-type]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)  # type: ignore[arg-type]

    registry = RegistryManager(settings.config_path)
    _attach_state(
        app,
        settings=settings,
        auth_settings=auth_settings,
        registry=registry,
        db=db,
        auth_service=auth_service,
        room_manager=room_manager,
        room_connections=room_connections,
    )

    logger.info("lobby server ready")
    return app


def _attach_state(  # noqa: PLR0913
    app: Starlette,
    *,
    settings: LobbyServerSettings,
    auth_settings: AuthSettings,
    registry: RegistryManager,
    db: Database,
    auth_service: AuthService,
    room_manager: LobbyRoomManager,
    room_connections: RoomConnectionManager,
) -> None:
    app.state.db = db
    app.state.settings = settings
    app.state.auth_settings = auth_settings
    app.state.registry = registry

    templates = create_templates()
    dev_mode = APP_VERSION == "dev"
    vite_dev_url = settings.vite_dev_url

    if vite_dev_url:
        # Vite dev server: templates load assets from Vite for HMR.
        # CSS URLs point to SCSS source files — Vite compiles and serves them as CSS.
        # JS URLs point to TS entry points — Vite serves them as ES modules.
        templates.env.globals["vite_dev"] = True
        templates.env.globals["vite_dev_url"] = vite_dev_url
        templates.env.globals["lobby_css_url"] = f"{vite_dev_url}/src/styles/lobby-app.scss"
        templates.env.globals["lobby_js_url"] = f"{vite_dev_url}/src/lobby/index.ts"
        templates.env.globals["game_css_url"] = f"{vite_dev_url}/src/styles/game-app.scss"
        templates.env.globals["game_js_url"] = f"{vite_dev_url}/src/index.ts"
        game_assets_available = True
    else:
        # Production (or standalone dev without Vite): read Vite manifest
        templates.env.globals["vite_dev"] = False
        templates.env.globals["vite_dev_url"] = ""
        manifest = load_vite_manifest(settings.game_assets_dir)
        urls = resolve_vite_asset_urls(manifest)
        templates.env.globals["lobby_css_url"] = urls.get("lobby_css", "")
        templates.env.globals["lobby_js_url"] = urls.get("lobby_js", "")
        templates.env.globals["game_css_url"] = urls.get("game_css", "")
        templates.env.globals["game_js_url"] = urls.get("game_js", "")
        game_assets_available = bool(urls.get("game_js"))

    templates.env.globals["app_version"] = APP_VERSION
    templates.env.globals["git_commit"] = GIT_COMMIT
    templates.env.globals["current_year"] = datetime.now(tz=UTC).year
    templates.env.globals["dev_mode"] = dev_mode
    app.state.templates = templates
    app.state.game_assets_available = game_assets_available
    app.state.auth_service = auth_service
    app.state.room_manager = room_manager
    app.state.room_connections = room_connections


def get_app() -> Starlette:  # pragma: no cover  # deadcode: ignore
    """Factory function for uvicorn --factory lobby.server.app:get_app."""
    s = LobbyServerSettings()
    auth = AuthSettings()  # ty: ignore[missing-argument]
    setup_logging(log_dir=s.log_dir)
    return create_app(settings=s, auth_settings=auth)
