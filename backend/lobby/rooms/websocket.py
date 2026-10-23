from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError

from lobby.game_transition import GameTransitionError, create_game_on_server, sign_player_tickets
from lobby.players import LobbyPlayer
from lobby.rooms.messages import (
    LobbyChatMessage,
    LobbyLeaveRoomMessage,
    LobbySetReadyMessage,
    LobbyStartGameMessage,
    parse_lobby_message,
)
from lobby.websocket_utils import check_origin
from shared.websocket import QueuedWebSocket, accept_websocket, reject_websocket

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from lobby.occupancy import Occupancy
    from lobby.rooms.manager import LobbyRoomManager
    from lobby.rooms.models import LobbyRoom
    from lobby.settings import LobbyServerSettings
    from shared.auth.settings import AuthSettings

logger = structlog.get_logger()


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
        await _cleanup_connection(player, ctx)


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

        async with room.join_lock:
            result = ctx.room_manager.join_room(room_id=ctx.room_id, player=player)
            if isinstance(result, str):
                _reject_join(player, ctx, reason=result)
                return False

            player.send(result)
            logger.info(
                "player joined room", room_id=ctx.room_id, username=player.username, player_count=room.player_count
            )
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
    while True:
        message = await player.connection.receive()
        try:
            parsed = parse_lobby_message(message["text"])
        except json.JSONDecodeError:
            player.send({"type": "error", "message": "Invalid JSON"})
            continue
        except (ValueError, ValidationError) as e:
            player.send({"type": "error", "message": str(e)})
            continue

        if isinstance(parsed, LobbySetReadyMessage):
            _handle_set_ready(player, ctx, message=parsed)
        elif isinstance(parsed, LobbyStartGameMessage):
            game_started = await _handle_start_game(player, ctx)
            if game_started:
                return
        elif isinstance(parsed, LobbyChatMessage):
            _handle_chat(player, ctx, message=parsed)
        elif isinstance(parsed, LobbyLeaveRoomMessage):
            player.connection.close()
            return


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
    Handle start_game — only the owner can trigger game transition.

    Acquires join_lock only for the atomic start_game() call which sets transitioning=True. The lock is released BEFORE
    the network call in _transition_to_game(), so concurrent joins are rejected quickly with "room_transitioning"
    instead of blocking on the lock.
    """
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None:
        player.send({"type": "error", "message": "not_in_room"})
        return False

    async with room.join_lock:
        error = ctx.room_manager.start_game(ctx.room_id, player.connection_id)
        if error is not None:
            player.send({"type": "error", "message": error})
            return False

    return await _transition_to_game(room, ctx)


async def _transition_to_game(room: LobbyRoom, ctx: _RoomContext) -> bool:
    """
    Create the game, then deliver ``game_starting`` and dispose of the room.

    Return True when the game was created. Each attempt gets a fresh game id: a failure may mean the game server created
    the game anyway (a timeout after the POST arrived), and that orphan must not make the next start collide with it.
    Before the game server answers 201 any exception is undone by ``_recover_failed_start`` (a cancellation, which only
    server shutdown causes, is not). After it the game exists with every signed ticket: each seated player gets
    ``game_starting`` and a 1000 close, enqueued, and the room is removed. Transitioning is never cleared, the state is
    never rebroadcast and creation is never retried.
    """
    game_id = str(uuid.uuid4())
    log = logger.bind(room_id=room.room_id, game_id=game_id)
    log.info("game transition starting", player_count=room.player_count)

    try:
        ws_url, ticket_map = await _create_game(room, ctx, game_id=game_id)
    except GameTransitionError as e:
        log.exception("failed to create game")
        _recover_failed_start(room, ctx, reason=str(e))
        return False
    except Exception:
        log.exception("unexpected error creating game")
        _recover_failed_start(room, ctx, reason="internal error")
        return False

    ctx.room_manager.remove_room(room.room_id)
    for connection_id, member in room.players.items():
        member.player.send(
            {
                "type": "game_starting",
                "ws_url": ws_url,
                "game_ticket": ticket_map[connection_id],
                "game_id": game_id,
                "game_client_url": ctx.settings.game_client_url,
            },
        )
        member.player.connection.close()

    log.info("game transition complete", ws_url=ws_url)
    return True


async def _create_game(room: LobbyRoom, ctx: _RoomContext, *, game_id: str) -> tuple[str, dict[str, str]]:
    """
    Sign a ticket per seated human and create the game; return the game server URL and the tickets by connection.

    The attempt hands the seated users to the game whatever its outcome, before the caller releases their seats: a
    failure may mean the game server created the game anyway.
    """
    players_for_tickets = [
        (member.player.user_id, member.player.username, conn_id) for conn_id, member in room.players.items()
    ]
    player_specs, ticket_map = sign_player_tickets(
        players=players_for_tickets,
        game_id=game_id,
        ticket_secret=ctx.auth_settings.game_ticket_secret,
    )
    try:
        ws_url = await create_game_on_server(
            game_id=game_id,
            players=player_specs,
            num_ai_players=room.num_ai_players,
            settings=ctx.settings,
        )
    finally:
        ctx.occupancy.hand_to_game(member.player.user_id for member in room.players.values())

    return ws_url, ticket_map


def _recover_failed_start(room: LobbyRoom, ctx: _RoomContext, *, reason: str) -> None:
    """
    Reopen the room after a start that failed before the game was created, and resync every client.

    ``clear_transitioning`` resets the ready flags and releases the seats of players who left meanwhile, dropping the
    room when nobody is left. Through this handler the room always survives, since the host runs the transition in its
    own handler and so cannot leave during it; the dropped-room return is kept for C20, whose shared ``start_game`` runs
    the transition for rooms and matchmaking alike.
    """
    ctx.room_manager.clear_transitioning(room.room_id)
    if ctx.room_manager.get_room(room.room_id) is None:
        return

    _send_room_state(room)
    _broadcast(room, {"type": "error", "message": f"Failed to start game: {reason}"})


def _handle_chat(player: LobbyPlayer, ctx: _RoomContext, *, message: LobbyChatMessage) -> None:
    """
    Broadcast a chat message to the room, its sender included: the client shows only the echo.
    """
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is not None:
        _broadcast(room, {"type": "chat", "player_name": player.username, "text": message.text})


async def _cleanup_connection(player: LobbyPlayer, ctx: _RoomContext) -> None:
    """
    Release the player's seat once the socket ends and tell the rest of the room.

    Acquires join_lock so that cleanup waits for any in-progress join to finish. A player leaving a transitioning room
    keeps the seat (``leave_room``), so nothing is announced.
    """
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None:
        return

    async with room.join_lock:
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
