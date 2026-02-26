"""WebSocket handler for lobby room interactions."""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
import structlog
from pydantic import ValidationError
from starlette.websockets import WebSocket, WebSocketDisconnect

from lobby.rooms.messages import (
    LobbyChatMessage,
    LobbyLeaveRoomMessage,
    LobbyPingMessage,
    LobbySetReadyMessage,
    parse_lobby_message,
)
from shared.auth.game_ticket import create_signed_ticket

if TYPE_CHECKING:
    from lobby.registry.manager import RegistryManager
    from lobby.rooms.connections import RoomConnectionManager
    from lobby.rooms.manager import LobbyRoomManager
    from lobby.server.settings import LobbyServerSettings
    from shared.auth.settings import AuthSettings

logger = structlog.get_logger()


class _RoomContext:
    """Bundles per-connection state extracted from app.state."""

    __slots__ = (
        "auth_settings",
        "connection_id",
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
        self.connection_id: str = str(uuid.uuid4())
        self.username: str = websocket.user.username


async def room_websocket(websocket: WebSocket) -> None:
    """Handle a WebSocket connection for a lobby room."""
    if not _check_origin(websocket):
        await websocket.close(code=4003, reason="forbidden_origin")
        return

    if not websocket.user.is_authenticated:
        await websocket.close(code=4001, reason="unauthorized")
        return

    await websocket.accept()
    ctx = _RoomContext(websocket)

    log = logger.bind(room_id=ctx.room_id, username=ctx.username)

    room = ctx.room_manager.get_room(ctx.room_id)
    if room is None:
        log.info("join rejected", reason="room_not_found")
        await websocket.send_json({"type": "error", "message": "room_not_found"})
        await websocket.close(code=4000, reason="room_not_found")
        return

    # Serialize the entire join flow (join → ack → register → broadcast) under
    # a per-room lock so that concurrent connections cannot interleave their
    # join sequences.  Without this, coroutine scheduling at any ``await``
    # inside the block can let another player's broadcast reach a connection
    # that hasn't received its own ``room_joined`` yet.
    async with room.join_lock:
        result = ctx.room_manager.join_room(
            ctx.connection_id,
            ctx.room_id,
            websocket.user.user_id,
            ctx.username,
        )
        if isinstance(result, str):
            log.info("join rejected", reason=result)
            await websocket.send_json({"type": "error", "message": result})
            await websocket.close(code=4000, reason=result)
            return

        await websocket.send_json(result)
        ctx.room_connections.add(ctx.room_id, ctx.connection_id, websocket)
        log.info("player joined room", player_count=room.player_count)
        await _broadcast_player_joined(ctx)

    try:
        await _message_loop(websocket, ctx)
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover — defensive catch-all
        log.exception("unexpected error in room websocket")
    finally:
        await _cleanup_connection(ctx)


def _check_origin(websocket: WebSocket) -> bool:
    settings: LobbyServerSettings = websocket.app.state.settings
    ws_allowed_origin = settings.ws_allowed_origin
    if not ws_allowed_origin:
        return True
    origin = websocket.headers.get("origin", "")
    return origin == ws_allowed_origin


async def _broadcast_player_joined(ctx: _RoomContext) -> None:
    room = ctx.room_manager.get_room(ctx.room_id)
    if room is not None:
        await ctx.room_connections.broadcast(
            ctx.room_id,
            {
                "type": "player_joined",
                "player_name": ctx.username,
                "players": [p.model_dump() for p in room.get_player_info()],
            },
            exclude=ctx.connection_id,
        )


async def _message_loop(websocket: WebSocket, ctx: _RoomContext) -> None:
    while True:
        raw = await websocket.receive_text()
        try:
            message = parse_lobby_message(raw)
        except (ValueError, ValidationError) as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            continue

        if isinstance(message, LobbySetReadyMessage):
            game_started = await _handle_set_ready(websocket, ctx, message)
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
) -> bool:
    """Handle a set_ready message, potentially triggering game creation.

    Return True when a game transition occurred and the connection was closed.
    """
    result = ctx.room_manager.set_ready(ctx.connection_id, ready=message.ready)
    if isinstance(result, str):
        await websocket.send_json({"type": "error", "message": result})
        return False

    room_id_result, all_ready = result

    log = logger.bind(room_id=room_id_result, username=ctx.username)
    log.info("player ready changed", ready=message.ready, all_ready=all_ready)

    room = ctx.room_manager.get_room(room_id_result)
    if room is not None:
        await ctx.room_connections.broadcast(
            room_id_result,
            {
                "type": "player_ready_changed",
                "players": [p.model_dump() for p in room.get_player_info()],
            },
        )

    if all_ready:
        return await _transition_to_game(room_id_result, ctx)

    return False


async def _transition_to_game(room_id: str, ctx: _RoomContext) -> bool:
    """Create a game on the game server and notify all players.

    Return True when the game was created and connections were closed.
    """
    room = ctx.room_manager.get_room(room_id)
    if room is None:  # pragma: no cover — race condition guard
        return False

    log = logger.bind(room_id=room_id)
    log.info("game transition starting", player_count=room.player_count)

    # Sign game tickets for each player
    player_specs = []
    ticket_map: dict[str, str] = {}  # connection_id -> signed_ticket
    for conn_id, player in room.players.items():
        signed_ticket = create_signed_ticket(
            player.user_id,
            player.username,
            room_id,
            ctx.auth_settings.game_ticket_secret,
        )
        player_specs.append(
            {"name": player.username, "user_id": player.user_id, "game_ticket": signed_ticket},
        )
        ticket_map[conn_id] = signed_ticket

    try:
        ws_url = await _create_game_on_server(
            room_id,
            player_specs,
            room.num_ai_players,
            ctx.registry,
        )
    except GameTransitionError as e:
        log.exception("failed to create game")
        ctx.room_manager.clear_transitioning(room_id)
        await ctx.room_connections.broadcast(
            room_id,
            {"type": "error", "message": f"Failed to start game: {e}"},
        )
        return False

    game_client_url = ctx.settings.game_client_url

    # Send game_starting to each player with their individual ticket
    player_conn_ids = list(room.players)
    total = len(player_conn_ids)
    failed_count = 0
    for conn_id in player_conn_ids:
        ticket = ticket_map.get(conn_id, "")
        delivered = await ctx.room_connections.send_to(
            conn_id,
            {
                "type": "game_starting",
                "ws_url": ws_url,
                "game_ticket": ticket,
                "game_id": room_id,
                "game_client_url": game_client_url,
            },
        )
        if not delivered:
            failed_count += 1
            player = room.players.get(conn_id)
            player_name = player.username if player else "unknown"
            log.warning(
                "failed to deliver game_starting message",
                connection_id=conn_id,
                player_name=player_name,
            )

    if failed_count > 0:
        log.error(
            "game_starting delivery failures",
            failed=failed_count,
            total=total,
        )

    log.info("game transition complete", ws_url=ws_url)
    ctx.room_manager.remove_room(room_id)
    await ctx.room_connections.close_connections(room_id)
    return True


class GameTransitionError(Exception):
    pass


_HTTP_CREATED = HTTPStatus.CREATED


async def _create_game_on_server(
    game_id: str,
    players: list[dict],
    num_ai_players: int,
    registry: RegistryManager,
) -> str:
    """Call POST /games on a game server. Return the game server WebSocket URL."""
    await registry.check_health()
    healthy_servers = registry.get_healthy_servers()
    if not healthy_servers:
        raise GameTransitionError("No healthy game servers available")

    server = healthy_servers[0]
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{server.url}/games",
                json={
                    "game_id": game_id,
                    "players": players,
                    "num_ai_players": num_ai_players,
                },
            )
            if response.status_code != _HTTP_CREATED:
                raise GameTransitionError(
                    f"Game server returned {response.status_code}: {response.text}",
                )
        except httpx.RequestError as e:
            raise GameTransitionError(f"Failed to connect to game server: {e}") from e

    ws_url = server.client_url.replace("http://", "ws://").replace("https://", "wss://")
    return f"{ws_url}/ws/{game_id}"


async def _handle_chat(ctx: _RoomContext, message: LobbyChatMessage) -> None:
    """Broadcast a chat message to the room."""
    await ctx.room_connections.broadcast(
        ctx.room_id,
        {"type": "chat", "player_name": ctx.username, "text": message.text},
    )


async def _handle_leave(websocket: WebSocket, _ctx: _RoomContext) -> None:
    """Handle a leave_room message. Closing triggers _cleanup_connection via the finally block."""
    await websocket.close()


async def _cleanup_connection(ctx: _RoomContext) -> None:
    """Clean up after a disconnected connection."""
    username = ctx.username
    room_id = ctx.room_manager.leave_room(ctx.connection_id)
    ctx.room_connections.remove(ctx.connection_id)
    if room_id:
        logger.info("player left room", room_id=room_id, username=username)
        room = ctx.room_manager.get_room(room_id)
        if room is not None:
            await ctx.room_connections.broadcast(
                room_id,
                {
                    "type": "player_left",
                    "player_name": username,
                    "players": [p.model_dump() for p in room.get_player_info()],
                },
            )
