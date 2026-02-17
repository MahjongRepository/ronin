import secrets
import string
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates

from lobby.games.service import RoomCreationError

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

PLAYER_NAME_SUFFIX_LENGTH = 6


def create_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def _generate_player_name() -> str:
    chars = string.ascii_lowercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(PLAYER_NAME_SUFFIX_LENGTH))
    return f"Player_{suffix}"


def _build_websocket_url(server_url: str, room_id: str) -> str:
    """Build a WebSocket URL from a server HTTP URL and room ID."""
    ws_url = server_url.replace("http://", "ws://").replace("https://", "wss://")
    return f"{ws_url}/ws/{room_id}"


async def lobby_page(request: Request) -> Response:
    settings = request.app.state.settings
    templates: Jinja2Templates = request.app.state.templates
    games_service = request.app.state.games_service
    rooms = await games_service.list_rooms()
    player_name = _generate_player_name()

    for room in rooms:
        room["websocket_url"] = _build_websocket_url(room["server_url"], room["room_id"])

    return templates.TemplateResponse(
        request,
        "lobby.html",
        {
            "rooms": rooms,
            "player_name": player_name,
            "game_client_url": settings.game_client_url,
            "error": None,
        },
    )


async def create_room_and_redirect(request: Request) -> Response:
    settings = request.app.state.settings
    templates: Jinja2Templates = request.app.state.templates
    games_service = request.app.state.games_service
    form = await request.form()
    player_name = form.get("player_name", _generate_player_name())

    try:
        result = await games_service.create_room(num_ai_players=3)
    except RoomCreationError as e:
        rooms = await games_service.list_rooms()
        for room in rooms:
            room["websocket_url"] = _build_websocket_url(room["server_url"], room["room_id"])
        return templates.TemplateResponse(
            request,
            "lobby.html",
            {
                "rooms": rooms,
                "player_name": player_name,
                "game_client_url": settings.game_client_url,
                "error": str(e),
            },
        )

    params = urlencode({"ws_url": result.websocket_url, "player_name": player_name})
    redirect_url = f"{settings.game_client_url}/?{params}#/room/{result.room_id}"
    return RedirectResponse(redirect_url, status_code=303)
