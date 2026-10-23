from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError

from lobby.game_transition import GameStartError, start_game
from lobby.players import LobbyPlayer
from lobby.rooms.messages import (
    LobbyChatMessage,
    LobbyClientMessage,
    LobbyLeaveRoomMessage,
    LobbySetReadyMessage,
    LobbyStartGameMessage,
    parse_lobby_message,
)
from lobby.websocket_utils import check_origin
from shared.rate_limit import TokenBucket
from shared.websocket import QueuedWebSocket, accept_websocket, reject_websocket

if TYPE_CHECKING:
    from starlette.types import Message
    from starlette.websockets import WebSocket

    from lobby.occupancy import Occupancy
    from lobby.rooms.manager import LobbyRoomManager
    from lobby.rooms.models import LobbyRoom
    from lobby.settings import LobbyServerSettings
    from shared.auth.settings import AuthSettings

logger = structlog.get_logger()

_RATE_LIMIT_RATE = 5.0
_RATE_LIMIT_BURST = 10
_RATE_LIMITED = "rate_limited"
_BINARY_FRAME = "Binary frames are not supported"


class _RoomContext:
    """
    Bundles per-connection state extracted from app.state.
    """

    __slots__ = (
        "auth_settings",
        "occupancy",
        "room_id",
        "room_manager",
        "settings",
    )

    def __init__(self, websocket: WebSocket) -> None:
        self.room_id: str = websocket.path_params["room_id"]
        self.settings: LobbyServerSettings = websocket.app.state.settings
        self.auth_settings: AuthSettings = websocket.app.state.auth_settings
        self.room_manager: LobbyRoomManager = websocket.app.state.room_manager
        self.occupancy: Occupancy = websocket.app.state.occupancy


async def room_websocket(websocket: WebSocket) -> None:
    """
    Handle a WebSocket connection for a lobby room; this task owns the connection's writer.
    """
    if not check_origin(websocket):
        await reject_websocket(websocket, code=4003, reason="forbidden_origin")
        return

    if not websocket.user.is_authenticated:
        await reject_websocket(websocket, code=4001, reason="unauthorized")
        return

    if not await accept_websocket(websocket):
        return

    connection_id = str(uuid.uuid4())
    player = LobbyPlayer(
        connection_id=connection_id,
        user_id=websocket.user.user_id,
        username=websocket.user.username,
        connection=QueuedWebSocket(websocket, connection_id=connection_id),
    )
    player.connection.start_writer()
    try:
        await _serve_player(player, _RoomContext(websocket))
    finally:
        await player.connection.stop_writer()


async def _serve_player(player: LobbyPlayer, ctx: _RoomContext) -> None:
    """
    Seat the player and serve their messages until the socket ends; their seat is released whatever happens.
    """
    try:
        if await _join(player, ctx):
            await _message_loop(player, ctx)
    except ConnectionError:
        pass
    except Exception:
        logger.exception("unexpected error in room websocket", room_id=ctx.room_id, username=player.username)
    finally:
        _cleanup_connection(player, ctx)


async def _join(player: LobbyPlayer, ctx: _RoomContext) -> bool:
    """
    Seat the player, acknowledge it and announce it; return False when the join was rejected.

    The seat, the ack and the announcement are one synchronous step, so no broadcast can reach the player before its
    ``room_joined`` and none made after the seating misses it. It runs inside the handler's ``try/finally``, so the seat
    (and the host) is freed however the connection ends. The check that the user is not playing a game, which asks the
    game server, runs first; ``join_room`` checks the rest of the occupancy rule, including a start that handed the user
    to a game while that lookup was in flight.
    """
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None:
        _reject_join(player, ctx, reason="room_not_found")
        return False

    with ctx.occupancy.admitting(player.user_id):
        game_conflict = await ctx.occupancy.find_game_conflict(player.user_id)
        if game_conflict is not None:
            _reject_join(player, ctx, reason=game_conflict)
            return False

        result = ctx.room_manager.join_room(room_id=ctx.room_id, player=player)
        if isinstance(result, str):
            _reject_join(player, ctx, reason=result)
            return False

        player.send(result)
        logger.info("player joined room", room_id=ctx.room_id, username=player.username, player_count=room.player_count)
        _broadcast(
            room,
            {
                "type": "player_joined",
                "player_name": player.username,
                "players": [p.model_dump() for p in room.get_player_info()],
                "can_start": room.can_start,
            },
            exclude=player.connection_id,
        )

    return True


def _reject_join(player: LobbyPlayer, ctx: _RoomContext, *, reason: str) -> None:
    logger.info("join rejected", room_id=ctx.room_id, username=player.username, reason=reason)
    player.send({"type": "error", "message": reason})
    player.connection.close(code=4000, reason=reason)


def _broadcast(room: LobbyRoom, message: dict, *, exclude: str | None = None) -> None:
    """
    Send a message to every player seated in the room, encoded once; ``exclude`` skips one connection.
    """
    payload = json.dumps(message)
    for connection_id, member in room.players.items():
        if connection_id != exclude:
            member.player.connection.send_text(payload)


def _send_room_state(room: LobbyRoom) -> None:
    _broadcast(
        room,
        {
            "type": "player_ready_changed",
            "players": [p.model_dump() for p in room.get_player_info()],
            "can_start": room.can_start,
        },
    )


async def _message_loop(player: LobbyPlayer, ctx: _RoomContext) -> None:
    """
    Serve the player's messages in order until the socket ends or the player starts the game or leaves.
    """
    bucket = TokenBucket(rate=_RATE_LIMIT_RATE, burst=_RATE_LIMIT_BURST)
    while True:
        message = _read_message(player, bucket=bucket, frame=await player.connection.receive())
        if isinstance(message, LobbySetReadyMessage):
            _handle_set_ready(player, ctx, message=message)
        elif isinstance(message, LobbyStartGameMessage):
            game_started = await _handle_start_game(player, ctx)
            if game_started:
                return
        elif isinstance(message, LobbyChatMessage):
            _handle_chat(player, ctx, message=message)
        elif isinstance(message, LobbyLeaveRoomMessage):
            player.connection.close()
            return


def _read_message(player: LobbyPlayer, *, bucket: TokenBucket, frame: Message) -> LobbyClientMessage | None:
    """
    Return the frame's room message, or None after answering the error that rejected it.

    Every frame counts against the player's rate limit before it is read, so invalid frames, which each get an error
    reply, count too; a frame over the limit is answered ``rate_limited`` and dropped, and the connection stays. A
    binary frame is answered with an error, since the room speaks JSON text.
    """
    if not bucket.consume():
        player.send({"type": "error", "message": _RATE_LIMITED})
        return None

    text = frame.get("text")
    if text is None:
        player.send({"type": "error", "message": _BINARY_FRAME})
        return None

    try:
        return parse_lobby_message(text)
    except json.JSONDecodeError:
        player.send({"type": "error", "message": "Invalid JSON"})
    except (ValueError, ValidationError) as e:
        player.send({"type": "error", "message": str(e)})

    return None


def _handle_set_ready(player: LobbyPlayer, ctx: _RoomContext, *, message: LobbySetReadyMessage) -> None:
    """
    Handle a set_ready message — broadcast state change, never auto-start.
    """
    room_or_error = ctx.room_manager.set_ready(ctx.room_id, player.connection_id, ready=message.ready)
    if isinstance(room_or_error, str):
        player.send({"type": "error", "message": room_or_error})
        return

    room = room_or_error

    logger.info(
        "player ready changed",
        room_id=ctx.room_id,
        username=player.username,
        ready=message.ready,
        can_start=room.can_start,
    )
    _send_room_state(room)


async def _handle_start_game(player: LobbyPlayer, ctx: _RoomContext) -> bool:
    """
    Start the game when the owner asks; return True when it was created.

    The manager marks the room transitioning in one synchronous step, so a join or a ready toggle arriving while the
    game is created gets ``room_transitioning``. A failed start reopens the room; after a successful one the room is
    removed: transitioning is never cleared, the state never rebroadcast and creation never retried.
    """
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None:
        player.send({"type": "error", "message": "not_in_room"})
        return False

    error = ctx.room_manager.start_game(ctx.room_id, player.connection_id)
    if error is not None:
        player.send({"type": "error", "message": error})
        return False

    try:
        game_id = await start_game(
            [member.player for member in room.players.values()],
            num_ai_players=room.num_ai_players,
            settings=ctx.settings,
            ticket_secret=ctx.auth_settings.game_ticket_secret,
            occupancy=ctx.occupancy,
        )
    except GameStartError as e:
        _recover_failed_start(room, ctx, reason=e.reason)
        return False

    ctx.room_manager.remove_room(room.room_id)
    logger.info("room handed to its game", room_id=room.room_id, game_id=game_id)
    return True


def _recover_failed_start(room: LobbyRoom, ctx: _RoomContext, *, reason: str) -> None:
    """
    Reopen the room after a start that failed before the game was created, and resync every client.

    ``clear_transitioning`` resets the ready flags and releases the seats of players who left meanwhile. The host runs
    the transition in its own handler and so cannot leave during it, so the room always survives here.
    """
    ctx.room_manager.clear_transitioning(room.room_id)
    _send_room_state(room)
    _broadcast(room, {"type": "error", "message": f"Failed to start game: {reason}"})


def _handle_chat(player: LobbyPlayer, ctx: _RoomContext, *, message: LobbyChatMessage) -> None:
    """
    Broadcast a chat message to the room, its sender included: the client shows only the echo.
    """
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is not None:
        _broadcast(room, {"type": "chat", "player_name": player.username, "text": message.text})


def _cleanup_connection(player: LobbyPlayer, ctx: _RoomContext) -> None:
    """
    Release the player's seat once the socket ends and tell the rest of the room.

    One synchronous step, so the new owner gets ``owner_changed`` before ``player_left`` and nothing interleaves. A
    player leaving a transitioning room keeps the seat (``leave_room``), so nothing is announced.
    """
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None:
        return

    was_host = room.host_connection_id == player.connection_id
    if not ctx.room_manager.leave_room(ctx.room_id, player.connection_id):
        return

    logger.info("player left room", room_id=ctx.room_id, username=player.username)
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None or room.transitioning:
        return

    if was_host and room.host_connection_id is not None:
        room.players[room.host_connection_id].player.send(
            {
                "type": "owner_changed",
                "is_owner": True,
                "can_start": room.can_start,
                "players": [p.model_dump() for p in room.get_player_info()],
            },
        )

    _broadcast(
        room,
        {
            "type": "player_left",
            "player_name": player.username,
            "players": [p.model_dump() for p in room.get_player_info()],
            "can_start": room.can_start,
        },
    )
