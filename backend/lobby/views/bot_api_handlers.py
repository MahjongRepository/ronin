from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from lobby.rooms.models import TOTAL_SEATS

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response


async def _parse_json_body(request: Request) -> dict | None:
    """
    Parse JSON body from request.

    Return None on failure.
    """
    try:
        body = await request.json()
    except ValueError, json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    return body


async def bot_auth(request: Request) -> Response:
    """POST /api/auth/bot {room_id} - create lobby session for bot to join room via WS."""
    body = await _parse_json_body(request)
    if body is None:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    room_id = body.get("room_id")
    if not isinstance(room_id, str) or not room_id:
        return JSONResponse({"error": "room_id is required as a non-empty string"}, status_code=400)

    room_manager = request.app.state.room_manager
    room = room_manager.get_room(room_id)
    if room is None:
        return JSONResponse({"error": "Room not found"}, status_code=404)

    auth_service = request.app.state.auth_service
    session = auth_service.create_session(
        user_id=request.user.user_id,
        username=request.user.username,
        account_type=request.user.account_type,
    )

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"
    return JSONResponse({"session_id": session.session_id, "room_id": room_id, "ws_url": ws_url})


async def bot_matchmaking_auth(request: Request) -> Response:
    """POST /api/matchmaking/join - create lobby session for bot to join matchmaking via WS."""
    auth_service = request.app.state.auth_service
    session = auth_service.create_session(
        user_id=request.user.user_id,
        username=request.user.username,
        account_type=request.user.account_type,
    )

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/matchmaking"
    return JSONResponse({"session_id": session.session_id, "ws_url": ws_url})


async def bot_create_room(request: Request) -> Response:
    """POST /api/rooms - create a room (bot API key auth via header)."""
    body = await _parse_json_body(request)
    if body is None:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    if "num_ai_players" in body:
        return JSONResponse(
            {"error": "num_ai_players is no longer supported; rooms always start with 4 bot seats"},
            status_code=400,
        )

    min_human_players = body.get("min_human_players", 1)
    if (
        isinstance(min_human_players, bool)
        or not isinstance(min_human_players, int)
        or not (1 <= min_human_players <= TOTAL_SEATS)
    ):
        return JSONResponse(
            {"error": "min_human_players must be an integer between 1 and 4"},
            status_code=400,
        )

    room_manager = request.app.state.room_manager
    room_id = str(uuid.uuid4())
    room_manager.create_room(room_id, min_human_players=min_human_players)

    auth_service = request.app.state.auth_service
    session = auth_service.create_session(
        user_id=request.user.user_id,
        username=request.user.username,
        account_type=request.user.account_type,
    )

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"
    return JSONResponse(
        {"room_id": room_id, "session_id": session.session_id, "ws_url": ws_url},
        status_code=201,
    )
