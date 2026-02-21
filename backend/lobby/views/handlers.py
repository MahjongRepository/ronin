"""Lobby view handlers for room listing, creation, and joining."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates

from lobby.games.service import RoomCreationError
from shared.auth.game_ticket import TICKET_TTL_SECONDS, GameTicket, sign_game_ticket

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.auth.models import AuthenticatedPlayer

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def create_templates() -> Jinja2Templates:
    """Create Jinja2 template engine for lobby HTML templates."""
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def build_websocket_url(server_url: str, room_id: str) -> str:
    """Build a WebSocket URL from a server HTTP URL and room ID."""
    ws_url = server_url.replace("http://", "ws://").replace("https://", "wss://")
    return f"{ws_url}/ws/{room_id}"


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


def _sign_ticket_and_redirect(
    user: AuthenticatedPlayer,
    room_id: str,
    websocket_url: str,
    game_ticket_secret: str,
    game_client_url: str,
) -> Response:
    """Sign a game ticket and redirect to the game client."""
    signed_ticket = create_signed_ticket(user.user_id, user.username, room_id, game_ticket_secret)
    params = urlencode({"ws_url": websocket_url, "game_ticket": signed_ticket})
    redirect_url = f"{game_client_url}/?{params}#/room/{room_id}"
    return RedirectResponse(redirect_url, status_code=303)


async def lobby_page(request: Request) -> Response:
    """GET / - render the lobby page with available rooms."""
    templates: Jinja2Templates = request.app.state.templates
    games_service = request.app.state.games_service
    user = request.user
    rooms = await games_service.list_rooms()

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
    """POST /rooms/new - create a room on a game server and redirect to the game client."""
    settings = request.app.state.settings
    auth_settings = request.app.state.auth_settings
    templates: Jinja2Templates = request.app.state.templates
    games_service = request.app.state.games_service
    user = request.user

    try:
        result = await games_service.create_room(num_ai_players=3)
    except RoomCreationError as e:
        rooms = await games_service.list_rooms()
        return _render_lobby_with_error(request, templates, rooms, user.username, str(e))

    return _sign_ticket_and_redirect(
        user,
        result.room_id,
        result.websocket_url,
        auth_settings.game_ticket_secret,
        settings.game_client_url,
    )


async def join_room_and_redirect(request: Request) -> Response:
    """POST /rooms/{room_id}/join - sign a game ticket for an existing room and redirect."""
    settings = request.app.state.settings
    auth_settings = request.app.state.auth_settings
    templates: Jinja2Templates = request.app.state.templates
    games_service = request.app.state.games_service
    user = request.user
    room_id = request.path_params["room_id"]

    rooms = await games_service.list_rooms()
    room = next((r for r in rooms if r["room_id"] == room_id), None)
    if room is None:
        return _render_lobby_with_error(request, templates, rooms, user.username, "Room not found")

    websocket_url = build_websocket_url(room["server_url"], room_id)
    return _sign_ticket_and_redirect(
        user,
        room_id,
        websocket_url,
        auth_settings.game_ticket_secret,
        settings.game_client_url,
    )
