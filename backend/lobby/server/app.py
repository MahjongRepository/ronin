from __future__ import annotations

import contextlib
import functools
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
from starlette.routing import BaseRoute, Mount, Route, WebSocketRoute
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
from lobby.game_transition import is_user_playing
from lobby.matchmaking.manager import MatchmakingManager
from lobby.matchmaking.websocket import matchmaking_websocket
from lobby.occupancy import Occupancy
from lobby.registry.manager import RegistryManager
from lobby.rooms.connections import RoomConnectionManager
from lobby.rooms.manager import LobbyRoomManager
from lobby.rooms.websocket import room_websocket
from lobby.server.middleware import SecurityHeadersMiddleware, SlashNormalizationMiddleware
from lobby.settings import LobbyServerSettings
from lobby.views import (
    create_room_and_redirect,
    create_templates,
    history_page,
    join_room_and_redirect,
    load_vite_manifest,
    lobby_page,
    matchmaking_page,
    play_page,
    replay_content,
    resolve_vite_asset_urls,
    room_page,
    storybook_page,
)
from lobby.views.auth_handlers import (
    login,
    login_page,
    logout,
    register,
    register_page,
)
from lobby.views.bot_api_handlers import bot_auth, bot_create_room, bot_matchmaking_auth
from shared.auth import AuthService, AuthSessionStore
from shared.auth.password import BcryptHasher
from shared.auth.settings import AuthSettings
from shared.build_info import APP_VERSION, GIT_COMMIT
from shared.db import Database, SqliteGameRepository, SqlitePlayerRepository
from shared.logging import setup_logging

logger = structlog.get_logger()

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from starlette.requests import Request


def _make_auth_error_handler(
    protected_api_paths: set[str],
) -> Callable[[Request, Exception], Awaitable[Response]]:
    """
    Build an HTTPException handler that rewrites 401s on protected JSON endpoints.
    """

    async def _auth_error_handler(request: Request, exc: Exception) -> Response:
        """
        Rewrite 401 errors on protected JSON endpoints to JSON responses.

        All other HTTP exceptions delegate to Starlette's default behavior (plain-text response with the exception
        detail).
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


def _create_seating(
    *,
    is_playing: Callable[[str], Awaitable[bool]],
) -> tuple[RoomConnectionManager, LobbyRoomManager, MatchmakingManager, Occupancy]:
    """
    Build the room and matchmaking managers and the occupancy rule they both enforce.
    """

    def find_lobby_conflict(user_id: str) -> str | None:
        """
        Apply the occupancy rule built below from the room and queue managers this function is injected into.
        """
        return occupancy.find_lobby_conflict(user_id)

    room_connections = RoomConnectionManager()
    room_manager = LobbyRoomManager(
        room_ttl_seconds=300,
        on_room_expired=lambda room_id, _conn_ids: room_connections.close_connections(
            room_id=room_id,
            code=4002,
            reason="room_expired",
        ),
        find_conflict=find_lobby_conflict,
    )
    matchmaking_manager = MatchmakingManager(find_conflict=find_lobby_conflict)
    occupancy = Occupancy(
        is_seated=room_manager.has_user_in_any_room,
        is_queued=matchmaking_manager.has_user,
        is_playing=is_playing,
    )
    return room_connections, room_manager, matchmaking_manager, occupancy


def create_app(
    settings: LobbyServerSettings | None = None,
    auth_settings: AuthSettings | None = None,  # required in production (via get_app)
    is_playing: Callable[[str], Awaitable[bool]] | None = None,
) -> Starlette:
    """
    Build the lobby app; ``is_playing`` replaces the game-server lookup of a user already playing (tests only).
    """
    if settings is None:  # pragma: no cover (entrypoint)
        settings = LobbyServerSettings()

    if auth_settings is None:  # pragma: no cover (entrypoint)
        auth_settings = AuthSettings()

    static_dir = Path(settings.static_dir).resolve()
    game_assets_dir = Path(settings.game_assets_dir).resolve()

    registry = RegistryManager(settings.config_path)
    if is_playing is None:
        is_playing = functools.partial(is_user_playing, registry=registry)

    room_connections, room_manager, matchmaking_manager, occupancy = _create_seating(is_playing=is_playing)

    routes: list[BaseRoute] = [
        # Protected HTML routes (redirect to login when unauthenticated)
        Route("/", protected_html(lobby_page), methods=["GET"], name="lobby_page"),
        Route("/history", protected_html(history_page), methods=["GET"], name="history_page"),
        Route("/play/history/{game_id}", public_route(play_page), methods=["GET"], name="replay_page"),
        Route("/play/storybook/board", public_route(play_page), methods=["GET"], name="storybook_board_page"),
        Route("/play/storybook/discards", public_route(play_page), methods=["GET"], name="storybook_discards_page"),
        Route("/play/storybook/hand", public_route(play_page), methods=["GET"], name="storybook_hand_page"),
        Route("/play/storybook/melds", public_route(play_page), methods=["GET"], name="storybook_melds_page"),
        Route("/play/storybook", public_route(play_page), methods=["GET"], name="storybook_page"),
        Route("/play/{game_id}", protected_html(play_page), methods=["GET"], name="play_page"),
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
        Route("/matchmaking", protected_html(matchmaking_page), methods=["GET"], name="matchmaking_page"),
        # Protected JSON routes (return 401 JSON when unauthenticated)
        Route("/servers", protected_api(list_servers), methods=["GET"], name="list_servers"),
        # WebSocket routes (auth handled inside the handlers)
        WebSocketRoute("/ws/rooms/{room_id}", room_websocket, name="room_websocket"),
        WebSocketRoute("/ws/matchmaking", matchmaking_websocket, name="matchmaking_websocket"),
        # Public routes
        Route("/health", public_route(health), methods=["GET"], name="health"),
        Route("/login", public_route(login_page), methods=["GET"], name="login_page"),
        Route("/login", public_route(login), methods=["POST"], name="login"),
        Route("/register", public_route(register_page), methods=["GET"], name="register_page"),
        Route("/register", public_route(register), methods=["POST"], name="register"),
        Route("/logout", public_route(logout), methods=["POST"], name="logout"),
        Route("/api/auth/bot", bot_only(bot_auth), methods=["POST"], name="bot_auth"),
        Route("/api/rooms", bot_only(bot_create_room), methods=["POST"], name="bot_create_room"),
        Route(
            "/api/matchmaking/join",
            bot_only(bot_matchmaking_auth),
            methods=["POST"],
            name="bot_matchmaking_auth",
        ),
        Route("/api/replays/{game_id}", public_route(replay_content), methods=["GET"], name="replay_content"),
    ]

    if APP_VERSION == "dev":
        routes.append(
            Route("/storybook", public_route(storybook_page), methods=["GET"], name="storybook_page"),
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

    player_repo = SqlitePlayerRepository(db)
    game_repo = SqliteGameRepository(db)

    session_store = AuthSessionStore()
    hasher = BcryptHasher(rounds=auth_settings.bcrypt_rounds)
    auth_service = AuthService(player_repo, session_store, password_hasher=hasher)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
        try:
            db.connect()
            session_store.start_cleanup()
            room_manager.start_reaper()
            yield
        finally:
            await room_manager.stop_reaper()
            await session_store.stop_cleanup()
            db.close()

    app = Starlette(
        routes=routes,
        lifespan=lifespan,
        exception_handlers={HTTPException: _make_auth_error_handler(protected_api_paths)},
    )
    app.add_middleware(SlashNormalizationMiddleware)
    app.add_middleware(AuthenticationMiddleware, backend=SessionOrApiKeyBackend(auth_service))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
    app.add_middleware(SecurityHeadersMiddleware, vite_dev_url=settings.vite_dev_url)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    _attach_state(
        app,
        settings=settings,
        auth_settings=auth_settings,
        registry=registry,
        db=db,
        game_repo=game_repo,
        auth_service=auth_service,
        room_manager=room_manager,
        room_connections=room_connections,
        matchmaking_manager=matchmaking_manager,
        occupancy=occupancy,
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
    game_repo: SqliteGameRepository,
    auth_service: AuthService,
    room_manager: LobbyRoomManager,
    room_connections: RoomConnectionManager,
    matchmaking_manager: MatchmakingManager,
    occupancy: Occupancy,
) -> None:
    app.state.db = db
    app.state.game_repo = game_repo
    app.state.settings = settings
    app.state.auth_settings = auth_settings
    app.state.registry = registry

    templates = create_templates()
    env_globals = cast("dict[str, object]", templates.env.globals)
    dev_mode = APP_VERSION == "dev"
    vite_dev_url = settings.vite_dev_url

    if vite_dev_url:
        # Vite dev server: templates load assets from Vite for HMR.
        # CSS URLs point to SCSS source files — Vite compiles and serves them as CSS.
        # JS URLs point to TS entry points — Vite serves them as ES modules.
        env_globals["vite_dev"] = True
        env_globals["vite_dev_url"] = vite_dev_url

        env_globals["lobby_css_url"] = f"{vite_dev_url}/src/styles/lobby-app.scss"
        env_globals["lobby_js_url"] = f"{vite_dev_url}/src/lobby/index.ts"
        env_globals["game_css_url"] = f"{vite_dev_url}/src/styles/game-app.scss"
        env_globals["game_js_url"] = f"{vite_dev_url}/src/index.ts"
        game_assets_available = True
    else:
        # Production (or standalone dev without Vite): read Vite manifest
        env_globals["vite_dev"] = False
        env_globals["vite_dev_url"] = ""

        manifest = load_vite_manifest(settings.game_assets_dir)
        urls = resolve_vite_asset_urls(manifest)

        env_globals["lobby_css_url"] = urls.get("lobby_css", "")
        env_globals["lobby_js_url"] = urls.get("lobby_js", "")
        env_globals["game_css_url"] = urls.get("game_css", "")
        env_globals["game_js_url"] = urls.get("game_js", "")
        game_assets_available = bool(urls.get("game_js"))

    env_globals["app_version"] = APP_VERSION
    env_globals["git_commit"] = GIT_COMMIT
    env_globals["current_year"] = datetime.now(tz=UTC).year
    env_globals["dev_mode"] = dev_mode

    app.state.templates = templates
    app.state.game_assets_available = game_assets_available
    app.state.auth_service = auth_service
    app.state.room_manager = room_manager
    app.state.room_connections = room_connections
    app.state.matchmaking_manager = matchmaking_manager
    app.state.occupancy = occupancy


def get_app() -> Starlette:  # pragma: no cover (entrypoint)  # deadcode: ignore
    """
    Factory function for uvicorn --factory lobby.server.app:get_app.
    """
    s = LobbyServerSettings()
    auth = AuthSettings()
    setup_logging(log_dir=s.log_dir)
    return create_app(settings=s, auth_settings=auth)
