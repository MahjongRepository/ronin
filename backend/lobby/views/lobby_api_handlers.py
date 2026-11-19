from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from lobby.auth.csrf import is_csrf_valid
from lobby.views.auth_handlers import ACCOUNT_RULES
from lobby.views.error_pages import json_csrf_rejection
from lobby.views.handlers import open_new_room
from lobby.views.json_body import parse_json_body

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

    from lobby.rooms.manager import LobbyRoomManager
    from shared.auth import AuthService

_NO_STORE = {"Cache-Control": "no-store"}


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

    return JSONResponse({"user": user, "limits": ACCOUNT_RULES}, headers=_NO_STORE)


async def lobby_rooms(request: Request) -> JSONResponse:
    """
    GET /api/lobby/rooms - the locally managed rooms and the id of the one the user is seated in, if any.
    """
    room_manager: LobbyRoomManager = request.app.state.room_manager
    return JSONResponse(
        {"rooms": room_manager.get_rooms_info(), "my_room": room_manager.find_user_room(request.user.user_id)},
        headers=_NO_STORE,
    )


async def lobby_create_room(request: Request) -> Response:
    """
    POST /api/lobby/rooms - create a local room and answer its id.
    """
    if await parse_json_body(request) is None:
        return JSONResponse({"error": "invalid_body"}, status_code=HTTPStatus.BAD_REQUEST, headers=_NO_STORE)

    if not is_csrf_valid(request):
        return json_csrf_rejection(request)

    room_id = open_new_room(request.app.state.room_manager)
    return JSONResponse({"room_id": room_id}, status_code=HTTPStatus.CREATED, headers=_NO_STORE)
