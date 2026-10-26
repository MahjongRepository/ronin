from __future__ import annotations

import contextlib
import functools
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from lobby.auth.backend import SessionOrApiKeyBackend
from lobby.auth.policy import (
    bot_only,
    protected_html,
    public_route,
    validate_route_auth_policy,
)
from lobby.game_transition import create_game_server_client, is_user_playing
from lobby.matchmaking.manager import MatchmakingManager
from lobby.matchmaking.websocket import matchmaking_websocket
from lobby.occupancy import Occupancy
from lobby.rooms.manager import LobbyRoomManager
from lobby.rooms.websocket import room_websocket
from lobby.server.middleware import SecurityHeadersMiddleware, SlashNormalizationMiddleware
from lobby.settings import LobbyServerSettings
from lobby.views import (
    GAME_ASSETS_PATH,
    BuiltGameClient,
    DevGameClient,
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
from lobby.views.bot_api_handlers import bot_create_room
from shared.auth import AuthService, AuthSessionStore
from shared.auth.password import BcryptHasher
from shared.auth.settings import AuthSettings
from shared.build_info import APP_VERSION, GIT_COMMIT
from shared.db import Database, SqliteGameRepository, SqlitePlayerRepository
from shared.logging import setup_logging

logger = structlog.get_logger()

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    import httpx
    from starlette.requests import Request


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "version": APP_VERSION, "commit": GIT_COMMIT})


def _create_seating(
    *,
    is_playing: Callable[[str], Awaitable[bool]],
) -> tuple[LobbyRoomManager, MatchmakingManager, Occupancy]:
    """
    Build the room and matchmaking managers and the occupancy rule they both enforce.
    """

    def find_lobby_conflict(user_id: str) -> str | None:
        """
        Apply the occupancy rule built below from the room and queue managers this function is injected into.
        """
        return occupancy.find_lobby_conflict(user_id)

    room_manager = LobbyRoomManager(room_ttl_seconds=300, find_conflict=find_lobby_conflict)
    matchmaking_manager = MatchmakingManager(find_conflict=find_lobby_conflict)
    occupancy = Occupancy(
        is_seated=room_manager.has_user_in_any_room,
        is_queued=matchmaking_manager.has_user,
        is_playing=is_playing,
    )
    return room_manager, matchmaking_manager, occupancy


def create_app(
    settings: LobbyServerSettings | None = None,
    auth_settings: AuthSettings | None = None,  # required in production (via get_app)
    is_playing: Callable[[str], Awaitable[bool]] | None = None,
    game_server_transport: httpx.AsyncBaseTransport | None = None,
    game_client_dev_transport: httpx.AsyncBaseTransport | None = None,
) -> Starlette:
    """
    Build the lobby app.

    ``is_playing`` replaces the game-server lookup of a user already playing, ``game_server_transport`` the network
    under the game server client, and ``game_client_dev_transport`` the network under the game client's dev-server proxy
    (tests only). The game server client is closed in the lifespan, but works without it, so a test that drives a
    handler directly can still start games.
    """
    if settings is None:  # pragma: no cover (entrypoint)
        settings = LobbyServerSettings()

    if auth_settings is None:  # pragma: no cover (entrypoint)
        auth_settings = AuthSettings()

    static_dir = Path(settings.static_dir).resolve()
    assets_dir = Path(settings.assets_dir).resolve()
    game_client = _create_game_client(settings, dev_transport=game_client_dev_transport)

    game_server = create_game_server_client(settings.game_server_url, transport=game_server_transport)
    if is_playing is None:
        is_playing = functools.partial(is_user_playing, game_server=game_server)

    room_manager, matchmaking_manager, occupancy = _create_seating(is_playing=is_playing)

    routes: list[BaseRoute] = [
        # Protected HTML routes (redirect to login when unauthenticated)
        Route("/", protected_html(lobby_page), methods=["GET"], name="lobby_page"),
        Route("/history", protected_html(history_page), methods=["GET"], name="history_page"),
        Route("/play/history/{game_id}", public_route(play_page), methods=["GET"], name="replay_page"),
        Route("/play/storybook/board", public_route(play_page), methods=["GET"], name="storybook_board_page"),
        Route("/play/storybook/discards", public_route(play_page), methods=["GET"], name="storybook_discards_page"),
        Route("/play/storybook/hand", public_route(play_page), methods=["GET"], name="storybook_hand_page"),
        Route("/play/storybook/melds", public_route(play_page), methods=["GET"], name="storybook_melds_page"),
        Route("/play/storybook/decisions", public_route(play_page), methods=["GET"], name="storybook_decisions_page"),
        Route("/play/storybook/table", public_route(play_page), methods=["GET"], name="storybook_table_page"),
        Route("/play/storybook/win", public_route(play_page), methods=["GET"], name="storybook_win_page"),
        Route("/play/storybook/draw", public_route(play_page), methods=["GET"], name="storybook_draw_page"),
        Route("/play/storybook/standings", public_route(play_page), methods=["GET"], name="storybook_standings_page"),
        Route("/play/storybook/loading", public_route(play_page), methods=["GET"], name="storybook_loading_page"),
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
        Route("/api/rooms", bot_only(bot_create_room), methods=["POST"], name="bot_create_room"),
        Route("/api/replays/{game_id}", public_route(replay_content), methods=["GET"], name="replay_content"),
    ]

    if APP_VERSION == "dev":
        routes.append(
            Route("/storybook", public_route(storybook_page), methods=["GET"], name="storybook_page"),
        )

    if static_dir.is_dir():
        routes.append(Mount("/static", app=StaticFiles(directory=str(static_dir)), name="static"))

    if assets_dir.is_dir():
        routes.append(Mount("/lobby-assets", app=StaticFiles(directory=str(assets_dir)), name="lobby_assets"))
    else:
        logger.warning("lobby assets directory not found, /lobby-assets/ will not be served", path=str(assets_dir))

    routes.extend(_game_client_routes(game_client))

    validate_route_auth_policy(routes)

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
            await db.open()
            session_store.start_cleanup()
            room_manager.start_reaper()
            yield
        finally:
            await room_manager.stop_reaper()
            await session_store.stop_cleanup()
            await game_server.aclose()
            await db.close()

    app = Starlette(routes=routes, lifespan=lifespan)
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

    app.state.game_client = game_client
    _attach_state(
        app,
        settings=settings,
        game_server=game_server,
        auth_settings=auth_settings,
        game_repo=game_repo,
        auth_service=auth_service,
        room_manager=room_manager,
        matchmaking_manager=matchmaking_manager,
        occupancy=occupancy,
    )

    logger.info("lobby server ready")
    return app


def _attach_state(  # noqa: PLR0913
    app: Starlette,
    *,
    settings: LobbyServerSettings,
    game_server: httpx.AsyncClient,
    auth_settings: AuthSettings,
    game_repo: SqliteGameRepository,
    auth_service: AuthService,
    room_manager: LobbyRoomManager,
    matchmaking_manager: MatchmakingManager,
    occupancy: Occupancy,
) -> None:
    app.state.game_repo = game_repo
    app.state.settings = settings
    app.state.game_server = game_server
    app.state.auth_settings = auth_settings

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
        env_globals["lobby_js_url"] = f"{vite_dev_url}/src/index.ts"
    else:
        # Production (or standalone dev without Vite): read Vite manifest
        env_globals["vite_dev"] = False
        env_globals["vite_dev_url"] = ""

        manifest = load_vite_manifest(settings.assets_dir)
        urls = resolve_vite_asset_urls(manifest)

        env_globals["lobby_css_url"] = urls.get("lobby_css", "")
        env_globals["lobby_js_url"] = urls.get("lobby_js", "")

    env_globals["app_version"] = APP_VERSION
    env_globals["git_commit"] = GIT_COMMIT
    env_globals["current_year"] = datetime.now(tz=UTC).year
    env_globals["dev_mode"] = dev_mode

    app.state.templates = templates
    app.state.auth_service = auth_service
    app.state.room_manager = room_manager
    app.state.matchmaking_manager = matchmaking_manager
    app.state.occupancy = occupancy


def _create_game_client(
    settings: LobbyServerSettings,
    *,
    dev_transport: httpx.AsyncBaseTransport | None,
) -> BuiltGameClient | DevGameClient:
    if settings.game_client_dev_url:
        return DevGameClient(origin=settings.game_client_dev_url, transport=dev_transport)

    return BuiltGameClient(directory=Path(settings.game_client_dir).resolve())


def _game_client_routes(game_client: BuiltGameClient | DevGameClient) -> list[BaseRoute]:
    """
    Serve the game client's files under ``/game-assets/``: proxied to its dev server, or from its build.
    """
    if isinstance(game_client, DevGameClient):
        return [
            Route(
                f"{GAME_ASSETS_PATH}/{{path:path}}",
                public_route(game_client.serve_asset),
                methods=["GET"],
                name="game_assets",
            ),
        ]

    if not game_client.directory.is_dir():
        logger.warning(
            "game client directory not found, the game client will not be served",
            path=str(game_client.directory),
        )
        return []

    return [Mount(GAME_ASSETS_PATH, app=StaticFiles(directory=str(game_client.directory)), name="game_assets")]


def get_app() -> Starlette:  # pragma: no cover (entrypoint)  # deadcode: ignore
    """
    Factory function for uvicorn --factory lobby.server.app:get_app.
    """
    s = LobbyServerSettings()
    auth = AuthSettings()
    setup_logging(log_dir=s.log_dir)
    return create_app(settings=s, auth_settings=auth)
