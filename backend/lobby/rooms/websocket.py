from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketDisconnected

from lobby.game_transition import GameTransitionError, create_game_on_server, sign_player_tickets
from lobby.rooms.messages import (
    LobbyChatMessage,
    LobbyLeaveRoomMessage,
    LobbyPingMessage,
    LobbySetReadyMessage,
    LobbyStartGameMessage,
    parse_lobby_message,
)
from lobby.websocket_utils import check_origin

if TYPE_CHECKING:
    from lobby.occupancy import Occupancy
    from lobby.registry.manager import RegistryManager
    from lobby.rooms.connections import RoomConnectionManager
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
        "connection_id",
        "occupancy",
        "registry",
        "room_connections",
        "room_id",
        "room_manager",
        "settings",
        "username",
    )

    def __init__(self, websocket: WebSocket) -> None:
        self.room_id: str = websocket.path_params["room_id"]
        self.settings: LobbyServerSettings = websocket.app.state.settings
        self.auth_settings: AuthSettings = websocket.app.state.auth_settings
        self.room_manager: LobbyRoomManager = websocket.app.state.room_manager
        self.room_connections: RoomConnectionManager = websocket.app.state.room_connections
        self.registry: RegistryManager = websocket.app.state.registry
        self.occupancy: Occupancy = websocket.app.state.occupancy

        self.connection_id: str = str(uuid.uuid4())
        self.username: str = websocket.user.username


async def room_websocket(websocket: WebSocket) -> None:
    """
    Handle a WebSocket connection for a lobby room.

    ``WebSocketDisconnected`` is a normal end too: it is what the next receive raises once another task closed this
    socket, or a send to it failed, while the handler was not waiting on a receive.
    """
    if not check_origin(websocket):
        await websocket.close(code=4003, reason="forbidden_origin")
        return

    if not websocket.user.is_authenticated:
        await websocket.close(code=4001, reason="unauthorized")
        return

    await websocket.accept()
    ctx = _RoomContext(websocket)
    log = logger.bind(room_id=ctx.room_id, username=ctx.username)

    try:
        if await _join(websocket, ctx):
            await _message_loop(websocket, ctx)
    except WebSocketDisconnect, WebSocketDisconnected:
        pass
    except Exception:
        log.exception("unexpected error in room websocket")
    finally:
        await _cleanup_connection(ctx)


async def _join(websocket: WebSocket, ctx: _RoomContext) -> bool:
    """
    Seat the connection, acknowledge it and announce it; return False when the join was rejected.

    The whole flow (join, ack, register, broadcast) runs under the room's ``join_lock`` so concurrent joins cannot
    interleave: otherwise another player's broadcast could reach a connection that has not received its own
    ``room_joined`` yet. It runs inside the handler's ``try/finally``, so a failed ack still frees the seat (and the
    host). The check that the user is not playing a game, which asks the game servers, runs before the lock;
    ``join_room`` checks the rest of the occupancy rule under it, including a start that handed the user to a game
    while that lookup was in flight.
    """
    log = logger.bind(room_id=ctx.room_id, username=ctx.username)
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None:
        await _reject_join(websocket, ctx, reason="room_not_found")
        return False

    with ctx.occupancy.admitting(websocket.user.user_id):
        game_conflict = await ctx.occupancy.find_game_conflict(websocket.user.user_id)
        if game_conflict is not None:
            await _reject_join(websocket, ctx, reason=game_conflict)
            return False

        async with room.join_lock:
            result = ctx.room_manager.join_room(
                connection_id=ctx.connection_id,
                room_id=ctx.room_id,
                user_id=websocket.user.user_id,
                username=ctx.username,
            )
            if isinstance(result, str):
                await _reject_join(websocket, ctx, reason=result)
                return False

            await websocket.send_json(result)
            ctx.room_connections.add(room_id=ctx.room_id, connection_id=ctx.connection_id, websocket=websocket)
            log.info("player joined room", player_count=room.player_count)
            await _broadcast_player_joined(ctx, room)

    return True


async def _reject_join(websocket: WebSocket, ctx: _RoomContext, *, reason: str) -> None:
    logger.info("join rejected", room_id=ctx.room_id, username=ctx.username, reason=reason)
    await websocket.send_json({"type": "error", "message": reason})
    await websocket.close(code=4000, reason=reason)


async def _broadcast_player_joined(ctx: _RoomContext, room: LobbyRoom) -> None:
    await ctx.room_connections.broadcast(
        room_id=ctx.room_id,
        message={
            "type": "player_joined",
            "player_name": ctx.username,
            "players": [p.model_dump() for p in room.get_player_info()],
            "can_start": room.can_start,
        },
        exclude=ctx.connection_id,
    )


async def _message_loop(websocket: WebSocket, ctx: _RoomContext) -> None:
    while True:
        raw = await websocket.receive_text()
        try:
            message = parse_lobby_message(raw)
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "message": "Invalid JSON"})
            continue
        except (ValueError, ValidationError) as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            continue

        if isinstance(message, LobbySetReadyMessage):
            await _handle_set_ready(websocket, ctx, message=message)
        elif isinstance(message, LobbyStartGameMessage):
            game_started = await _handle_start_game(websocket, ctx)
            if game_started:
                return
        elif isinstance(message, LobbyChatMessage):
            await _handle_chat(ctx, message)
        elif isinstance(message, LobbyLeaveRoomMessage):
            await _handle_leave(websocket, ctx)
            return
        elif isinstance(message, LobbyPingMessage):
            await websocket.send_json({"type": "pong"})


async def _handle_set_ready(
    websocket: WebSocket,
    ctx: _RoomContext,
    message: LobbySetReadyMessage,
) -> None:
    """
    Handle a set_ready message — broadcast state change, never auto-start.
    """
    result = ctx.room_manager.set_ready(ctx.connection_id, ready=message.ready)
    if isinstance(result, str):
        await websocket.send_json({"type": "error", "message": result})
        return

    room_id_result, can_start = result

    log = logger.bind(room_id=room_id_result, username=ctx.username)
    log.info("player ready changed", ready=message.ready, can_start=can_start)

    room = ctx.room_manager.get_room(room_id_result)
    if room is not None:
        await ctx.room_connections.broadcast(
            room_id=room_id_result,
            message={
                "type": "player_ready_changed",
                "players": [p.model_dump() for p in room.get_player_info()],
                "can_start": can_start,
            },
        )


async def _handle_start_game(websocket: WebSocket, ctx: _RoomContext) -> bool:
    """
    Handle start_game — only the owner can trigger game transition.

    Acquires join_lock only for the atomic start_game() call which sets transitioning=True. The lock is released BEFORE
    the network call in _transition_to_game(), so concurrent joins are rejected quickly with "room_transitioning"
    instead of blocking on the lock.
    """
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None:
        await websocket.send_json({"type": "error", "message": "not_in_room"})
        return False

    async with room.join_lock:
        error = ctx.room_manager.start_game(ctx.connection_id)
        if error is not None:
            await websocket.send_json({"type": "error", "message": error})
            return False

    return await _transition_to_game(room, ctx)


async def _transition_to_game(room: LobbyRoom, ctx: _RoomContext) -> bool:
    """
    Create the game, then deliver ``game_starting`` and dispose of the room.

    Return True when the game was created. Each attempt gets a fresh game id: a failure may mean the game server created
    the game anyway (a timeout after the POST arrived), and that orphan must not make the next start collide with it.
    Before the game server answers 201 any exception is undone by ``_recover_failed_start`` (a cancellation, which only
    server shutdown causes, is not). After it the game exists with every signed ticket, so delivery is best-effort and
    the room is removed and its connections closed whatever happens: transitioning is never cleared, the state is never
    rebroadcast and creation is never retried.
    """
    game_id = str(uuid.uuid4())
    log = logger.bind(room_id=room.room_id, game_id=game_id)
    log.info("game transition starting", player_count=room.player_count)

    try:
        ws_url, ticket_map = await _create_game(room, ctx, game_id=game_id)
    except GameTransitionError as e:
        log.exception("failed to create game")
        await _recover_failed_start(room, ctx, reason=str(e))
        return False
    except Exception:
        log.exception("unexpected error creating game")
        await _recover_failed_start(room, ctx, reason="internal error")
        return False

    try:
        await _deliver_game_starting(room, ctx, game_id=game_id, ws_url=ws_url, ticket_map=ticket_map)
    finally:
        ctx.room_manager.remove_room(room.room_id)
        await ctx.room_connections.close_connections(room_id=room.room_id)

    log.info("game transition complete", ws_url=ws_url)
    return True


async def _create_game(room: LobbyRoom, ctx: _RoomContext, *, game_id: str) -> tuple[str, dict[str, str]]:
    """
    Sign a ticket per seated human and create the game; return the game server URL and the tickets by connection.

    The attempt hands the seated users to the game whatever its outcome, before the caller releases their seats: a
    failure may mean the game server created the game anyway.
    """
    players_for_tickets = [(player.user_id, player.username, conn_id) for conn_id, player in room.players.items()]
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
            registry=ctx.registry,
        )
    finally:
        ctx.occupancy.hand_to_game(player.user_id for player in room.players.values())

    return ws_url, ticket_map


async def _recover_failed_start(room: LobbyRoom, ctx: _RoomContext, *, reason: str) -> None:
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

    await ctx.room_connections.broadcast(
        room_id=room.room_id,
        message={
            "type": "player_ready_changed",
            "players": [p.model_dump() for p in room.get_player_info()],
            "can_start": room.can_start,
        },
    )
    await ctx.room_connections.broadcast(
        room_id=room.room_id,
        message={"type": "error", "message": f"Failed to start game: {reason}"},
    )


async def _deliver_game_starting(
    room: LobbyRoom,
    ctx: _RoomContext,
    *,
    game_id: str,
    ws_url: str,
    ticket_map: dict[str, str],
) -> None:
    """
    Send each seated player ``game_starting`` with their ticket, logging every connection it does not reach.

    A player who left during the transition is skipped: their socket is gone, and the game server replaces them with AI.
    """
    log = logger.bind(room_id=room.room_id, game_id=game_id)
    recipients = [(conn_id, player) for conn_id, player in room.players.items() if not player.departed]
    failed_count = 0
    for conn_id, player in recipients:
        delivered = await ctx.room_connections.send_to(
            conn_id,
            {
                "type": "game_starting",
                "ws_url": ws_url,
                "game_ticket": ticket_map[conn_id],
                "game_id": game_id,
                "game_client_url": ctx.settings.game_client_url,
            },
        )
        if not delivered:
            failed_count += 1
            log.warning(
                "failed to deliver game_starting message",
                connection_id=conn_id,
                player_name=player.username,
            )

    if failed_count > 0:
        log.error("game_starting delivery failures", failed=failed_count, total=len(recipients))


async def _handle_chat(ctx: _RoomContext, message: LobbyChatMessage) -> None:
    """
    Broadcast a chat message to the room.
    """
    await ctx.room_connections.broadcast(
        room_id=ctx.room_id,
        message={"type": "chat", "player_name": ctx.username, "text": message.text},
    )


async def _handle_leave(websocket: WebSocket, _ctx: _RoomContext) -> None:
    """
    Handle a leave_room message.

    Closing triggers _cleanup_connection via the finally block.
    """
    await websocket.close()


async def _cleanup_connection(ctx: _RoomContext) -> None:
    """
    Clean up after a disconnected connection.

    Acquires join_lock so that cleanup waits for any in-progress join to finish (including room_connections
    registration). This prevents a race where host transfer targets a joining player whose connection isn't registered
    yet, causing the owner_changed message to be dropped. A player leaving a transitioning room keeps the seat
    (``leave_room``), so nothing is announced.
    """
    username = ctx.username
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None:
        ctx.room_manager.leave_room(ctx.connection_id)
        ctx.room_connections.remove(ctx.connection_id)
        return

    async with room.join_lock:
        was_host = room.host_connection_id == ctx.connection_id
        room_id = ctx.room_manager.leave_room(ctx.connection_id)
        ctx.room_connections.remove(ctx.connection_id)
        if room_id is None:
            return

        logger.info("player left room", room_id=room_id, username=username)
        room = ctx.room_manager.get_room(room_id)
        if room is None or room.transitioning:
            return

        if was_host and room.host_connection_id is not None:
            await ctx.room_connections.send_to(
                room.host_connection_id,
                {
                    "type": "owner_changed",
                    "is_owner": True,
                    "can_start": room.can_start,
                    "players": [p.model_dump() for p in room.get_player_info()],
                },
            )

        await ctx.room_connections.broadcast(
            room_id=room_id,
            message={
                "type": "player_left",
                "player_name": username,
                "players": [p.model_dump() for p in room.get_player_info()],
                "can_start": room.can_start,
            },
        )
