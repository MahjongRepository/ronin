"""Lobby view handlers for room listing, creation, and joining."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from lobby.server.csrf import get_or_create_csrf_token, set_csrf_cookie, validate_csrf

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.rooms.manager import LobbyRoomManager

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def create_templates() -> Jinja2Templates:
    """Create Jinja2 template engine for lobby HTML templates."""
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def _render_lobby_with_error(
    request: Request,
    templates: Jinja2Templates,
    rooms: list[dict],
    username: str,
    error: str,
) -> Response:
    """Render the lobby page with an error message."""
    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "lobby.html",
        {
            "rooms": rooms,
            "username": username,
            "error": error,
            "csrf_token": csrf_token,
        },
    )
    if is_new:  # pragma: no cover — CSRF validation guarantees cookie exists before this path
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response


async def lobby_page(request: Request) -> Response:
    """GET / - render the lobby page with locally managed rooms."""
    templates: Jinja2Templates = request.app.state.templates
    room_manager: LobbyRoomManager = request.app.state.room_manager
    user = request.user
    rooms = room_manager.get_rooms_info()

    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "lobby.html",
        {
            "rooms": rooms,
            "username": user.username,
            "error": None,
            "csrf_token": csrf_token,
        },
    )
    if is_new:
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response


async def create_room_and_redirect(request: Request) -> Response:
    """POST /rooms/new - create a local room and redirect to the room page."""
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    room_manager: LobbyRoomManager = request.app.state.room_manager
    room_id = str(uuid.uuid4())
    room_manager.create_room(room_id, num_ai_players=3)
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


async def join_room_and_redirect(request: Request) -> Response:
    """POST /rooms/{room_id}/join - validate room exists and redirect to room page."""
    form = await request.form()
    csrf_error = validate_csrf(request, form)
    if csrf_error:
        return csrf_error

    templates: Jinja2Templates = request.app.state.templates
    room_manager: LobbyRoomManager = request.app.state.room_manager
    user = request.user
    room_id = request.path_params["room_id"]

    room = room_manager.get_room(room_id)
    if room is None:
        rooms = room_manager.get_rooms_info()
        return _render_lobby_with_error(request, templates, rooms, user.username, "Room not found")

    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


async def room_page(request: Request) -> Response:
    """GET /rooms/{room_id} - render the room page."""
    templates: Jinja2Templates = request.app.state.templates
    room_manager: LobbyRoomManager = request.app.state.room_manager
    room_id = request.path_params["room_id"]

    room = room_manager.get_room(room_id)
    if room is None:
        return RedirectResponse("/", status_code=303)

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"

    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "room.html",
        {
            "room_id": room_id,
            "ws_url": ws_url,
            "username": request.user.username,
            "csrf_token": csrf_token,
        },
    )
    if is_new:
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response


async def styleguide_page(request: Request) -> Response:
    """Render the style guide page for development."""
    templates: Jinja2Templates = request.app.state.templates
    username = request.user.username if request.user.is_authenticated else None
    csrf_token, is_new = get_or_create_csrf_token(request)
    response = templates.TemplateResponse(
        request,
        "styleguide.html",
        {"username": username, "csrf_token": csrf_token},
    )
    if is_new:
        auth_settings = request.app.state.auth_settings
        set_csrf_cookie(response, csrf_token, cookie_secure=auth_settings.cookie_secure)
    return response


async def game_styleguide_page(request: Request) -> Response:
    """Render the game style guide page for development."""
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, "game-styleguide.html")


def load_vite_manifest(game_assets_dir: str) -> dict[str, dict]:
    """Load the Vite manifest mapping source paths to build outputs.

    Vite 6.x stores the manifest at <outDir>/.vite/manifest.json.
    """
    manifest_path = Path(game_assets_dir).resolve() / ".vite" / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        msg = f"Malformed manifest.json at {manifest_path}: {e}"
        raise ValueError(msg) from e
    if not isinstance(data, dict):
        msg = f"manifest.json must be a JSON object, got {type(data).__name__}"
        raise TypeError(msg)
    return data


def _resolve_css_url(entry: dict, base_path: str) -> str | None:
    """Extract CSS URL from a Vite manifest entry.

    Vite extracts CSS into the `css` array when building from a JS entry point
    that imports SCSS/CSS files.
    """
    css_files = entry.get("css", [])
    if css_files:
        return f"{base_path}/{css_files[0]}"
    return None


def resolve_vite_asset_urls(manifest: dict[str, dict], base_path: str = "/game-assets") -> dict[str, str]:
    """Extract asset URLs from Vite manifest entries.

    Two entry points:
    - src/index.ts -> game_js + game_css
    - src/lobby/index.ts -> lobby_js + lobby_css

    Return a flat dict with keys: game_js, game_css, lobby_js, lobby_css.
    All dict access uses .get() to gracefully handle partial manifests.
    """
    base_path = base_path.rstrip("/")
    urls: dict[str, str] = {}

    game_entry = manifest.get("src/index.ts", {})
    game_js = game_entry.get("file")
    if game_js:
        urls["game_js"] = f"{base_path}/{game_js}"
    game_css = _resolve_css_url(game_entry, base_path)
    if game_css:
        urls["game_css"] = game_css

    lobby_entry = manifest.get("src/lobby/index.ts", {})
    lobby_js = lobby_entry.get("file")
    if lobby_js:
        urls["lobby_js"] = f"{base_path}/{lobby_js}"
    lobby_css = _resolve_css_url(lobby_entry, base_path)
    if lobby_css:
        urls["lobby_css"] = lobby_css

    return urls


async def game_page(request: Request) -> Response:
    """GET /game — render the game client page."""
    templates: Jinja2Templates = request.app.state.templates
    if not request.app.state.game_assets_available:
        return PlainTextResponse("Game client assets not available", status_code=503)
    return templates.TemplateResponse(request, "game.html")
