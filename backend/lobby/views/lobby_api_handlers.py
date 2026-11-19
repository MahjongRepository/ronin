from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from lobby.auth.csrf import is_csrf_valid
from lobby.rooms.messages import CHAT_MAX_LENGTH
from lobby.views.auth_handlers import ACCOUNT_RULES
from lobby.views.error_pages import NO_STORE_HEADERS, json_csrf_rejection
from lobby.views.handlers import find_live_game_page, lobby_websocket_url, open_new_room
from lobby.views.history_handlers import HISTORY_GAMES_LIMIT, history_entries
from lobby.views.json_body import parse_json_body

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.rooms.manager import LobbyRoomManager
    from shared.auth import AuthService
    from shared.dal.game_repository import GameRepository


async def lobby_session(request: Request) -> JSONResponse:
    """
    GET /api/lobby/session - the signed-in user, if any, and the account limits the auth forms enforce.

    The admin flag is read from the account on every request, as ``admin_html`` does, so a revoke applies at once.
    """
    user = None
    if request.user.is_authenticated:
        auth_service: AuthService = request.app.state.auth_service
        is_admin = await auth_service.is_admin(user_id=request.user.user_id, username=request.user.username)
        user = {"username": request.user.username, "is_guest": request.user.is_guest, "is_admin": is_admin}

    return JSONResponse({"user": user, "limits": ACCOUNT_RULES}, headers=NO_STORE_HEADERS)


async def lobby_rooms(request: Request) -> JSONResponse:
    """
    GET /api/lobby/rooms - the locally managed rooms and the id of the one the user is seated in, if any.
    """
    room_manager: LobbyRoomManager = request.app.state.room_manager
    return JSONResponse(
        {"rooms": room_manager.get_rooms_info(), "my_room": room_manager.find_user_room(request.user.user_id)},
        headers=NO_STORE_HEADERS,
    )


async def lobby_create_room(request: Request) -> Response:
    """
    POST /api/lobby/rooms - create a local room and answer its id.
    """
    if await parse_json_body(request) is None:
        return JSONResponse({"error": "invalid_body"}, status_code=HTTPStatus.BAD_REQUEST, headers=NO_STORE_HEADERS)

    if not is_csrf_valid(request):
        return json_csrf_rejection(request)

    room_id = open_new_room(request.app.state.room_manager)
    return JSONResponse({"room_id": room_id}, status_code=HTTPStatus.CREATED, headers=NO_STORE_HEADERS)


async def lobby_room(request: Request) -> JSONResponse:
    """
    GET /api/lobby/rooms/{room_id} - what the room view opens the room's socket with.

    A room that is gone answers 404 with the game page of the game the user plays, if any: a room is removed once its
    game starts, and the game page recovers a lost handoff on its own.
    """
    room_manager: LobbyRoomManager = request.app.state.room_manager
    room_id = request.path_params["room_id"]

    room = room_manager.get_room(room_id)
    if room is None:
        return JSONResponse(
            {"error": "room_not_found", "game_url": await find_live_game_page(request)},
            status_code=HTTPStatus.NOT_FOUND,
            headers=NO_STORE_HEADERS,
        )

    return JSONResponse(
        {
            "room_name": room.name,
            "ws_url": lobby_websocket_url(request, f"/ws/rooms/{room_id}"),
            "chat_max_length": CHAT_MAX_LENGTH,
        },
        headers=NO_STORE_HEADERS,
    )


async def lobby_matchmaking(request: Request) -> JSONResponse:
    """
    GET /api/lobby/matchmaking - what the matchmaking view opens the queue's socket with.
    """
    return JSONResponse({"ws_url": lobby_websocket_url(request, "/ws/matchmaking")}, headers=NO_STORE_HEADERS)


async def lobby_history(request: Request) -> JSONResponse:
    """
    GET /api/lobby/history - the most recent completed games, newest first, as the user sees them.
    """
    game_repo: GameRepository = request.app.state.game_repo
    games = await game_repo.get_recent_completed_games(limit=HISTORY_GAMES_LIMIT)
    return JSONResponse(
        {"games": history_entries(games, request.user.user_id)},
        headers=NO_STORE_HEADERS,
    )
