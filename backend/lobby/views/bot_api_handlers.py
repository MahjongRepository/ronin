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

    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{request.url.netloc}/ws/rooms/{room_id}"
    return JSONResponse(
        {"room_id": room_id, "ws_url": ws_url},
        status_code=201,
    )
