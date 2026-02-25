"""Lobby view handlers for room listing, creation, and joining."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.templating import Jinja2Templates

from shared.auth.game_ticket import TICKET_TTL_SECONDS, GameTicket, sign_game_ticket

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.rooms.manager import LobbyRoomManager

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def create_templates() -> Jinja2Templates:
    """Create Jinja2 template engine for lobby HTML templates."""
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_signed_ticket(
    user_id: str,
    username: str,
    room_id: str,
    game_ticket_secret: str,
) -> str:
    """Create and sign a game ticket, returning the signed token string."""
    now = time.time()
    ticket = GameTicket(
        user_id=user_id,
        username=username,
        room_id=room_id,
        issued_at=now,
        expires_at=now + TICKET_TTL_SECONDS,
    )
    return sign_game_ticket(ticket, game_ticket_secret)


def _render_lobby_with_error(
    request: Request,
    templates: Jinja2Templates,
    rooms: list[dict],
    username: str,
    error: str,
) -> Response:
    """Render the lobby page with an error message."""
    return templates.TemplateResponse(
        request,
        "lobby.html",
        {
            "rooms": rooms,
            "username": username,
            "error": error,
        },
    )


async def lobby_page(request: Request) -> Response:
    """GET / - render the lobby page with locally managed rooms."""
    templates: Jinja2Templates = request.app.state.templates
    room_manager: LobbyRoomManager = request.app.state.room_manager
    user = request.user
    rooms = room_manager.get_rooms_info()

    return templates.TemplateResponse(
        request,
        "lobby.html",
        {
            "rooms": rooms,
            "username": user.username,
            "error": None,
        },
    )


async def create_room_and_redirect(request: Request) -> Response:
    """POST /rooms/new - create a local room and redirect to the room page."""
    room_manager: LobbyRoomManager = request.app.state.room_manager
    room_id = str(uuid.uuid4())
    room_manager.create_room(room_id, num_ai_players=3)
    return RedirectResponse(f"/rooms/{room_id}", status_code=303)


async def join_room_and_redirect(request: Request) -> Response:
    """POST /rooms/{room_id}/join - validate room exists and redirect to room page."""
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

    return templates.TemplateResponse(
        request,
        "room.html",
        {
            "room_id": room_id,
            "ws_url": ws_url,
            "username": request.user.username,
        },
    )


async def styleguide_page(request: Request) -> Response:
    """Render the style guide page for development."""
    templates: Jinja2Templates = request.app.state.templates
    username = request.user.username if request.user.is_authenticated else None
    return templates.TemplateResponse(request, "styleguide.html", {"username": username})


async def game_styleguide_page(request: Request) -> Response:
    """Render the game style guide page for development."""
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, "game-styleguide.html")


def load_game_assets_manifest(game_assets_dir: str) -> dict[str, str]:
    """Load the asset manifest mapping logical names to content-hashed filenames."""
    manifest_path = Path(game_assets_dir).resolve() / "manifest.json"
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


async def game_page(request: Request) -> Response:
    """GET /game — render the game client page."""
    templates: Jinja2Templates = request.app.state.templates
    game_assets: dict[str, str] = request.app.state.game_assets
    js_asset = game_assets.get("js")
    if not js_asset:
        return PlainTextResponse("Game client assets not available", status_code=503)
    return templates.TemplateResponse(
        request,
        "game.html",
        {"game_js_url": f"/game-assets/{js_asset}"},
    )
