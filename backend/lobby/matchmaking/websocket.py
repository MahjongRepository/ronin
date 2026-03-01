"""WebSocket handler for matchmaking queue."""

from __future__ import annotations

import contextlib
import json
import uuid
from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from lobby.game_transition import create_game_on_server, sign_player_tickets
from lobby.matchmaking.messages import MatchmakingPingMessage, parse_matchmaking_message
from lobby.matchmaking.models import QueueEntry
from lobby.websocket_utils import check_origin

if TYPE_CHECKING:
    from lobby.matchmaking.manager import MatchmakingManager
    from lobby.registry.manager import RegistryManager
    from lobby.rooms.manager import LobbyRoomManager
    from lobby.server.settings import LobbyServerSettings
    from shared.auth.settings import AuthSettings

logger = structlog.get_logger()


class _MatchmakingContext:
    """Bundles per-connection state extracted from app.state."""

    __slots__ = (
        "auth_settings",
        "connection_id",
        "matchmaking_manager",
        "registry",
        "room_manager",
        "settings",
        "user_id",
        "username",
    )

    def __init__(self, websocket: WebSocket) -> None:
        self.settings: LobbyServerSettings = websocket.app.state.settings
        self.auth_settings: AuthSettings = websocket.app.state.auth_settings
        self.matchmaking_manager: MatchmakingManager = websocket.app.state.matchmaking_manager
        self.room_manager: LobbyRoomManager = websocket.app.state.room_manager
        self.registry: RegistryManager = websocket.app.state.registry
        self.connection_id: str = str(uuid.uuid4())
        self.user_id: str = websocket.user.user_id
        self.username: str = websocket.user.username


async def matchmaking_websocket(websocket: WebSocket) -> None:
    """Handle a WebSocket connection for matchmaking."""
    if not check_origin(websocket):
        await websocket.close(code=4003, reason="forbidden_origin")
        return

    if not websocket.user.is_authenticated:
        await websocket.close(code=4001, reason="unauthorized")
        return

    await websocket.accept()
    ctx = _MatchmakingContext(websocket)

    try:
        if not await _try_join_queue(websocket, ctx):
            return

        await _message_loop(websocket)
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover -- defensive catch-all
        logger.exception("unexpected error in matchmaking websocket")
    finally:
        await _cleanup_connection(ctx)


async def _try_join_queue(websocket: WebSocket, ctx: _MatchmakingContext) -> bool:
    """Attempt to join the matchmaking queue.

    Return True if the player should enter the message loop (queued or re-queued
    after match failure). Return False if the connection was rejected or a game
    was successfully created.
    """
    log = logger.bind(username=ctx.username, connection_id=ctx.connection_id)

    # Cross-system guard: reject if user is already in a room
    if ctx.room_manager.has_user_in_any_room(ctx.user_id):
        log.info("matchmaking rejected", reason="already_in_room")
        await websocket.send_json({"type": "error", "message": "already_in_room"})
        await websocket.close(code=4000, reason="already_in_room")
        return False

    entry = QueueEntry(
        connection_id=ctx.connection_id,
        user_id=ctx.user_id,
        username=ctx.username,
        websocket=websocket,
    )

    matched = None
    position = 0
    duplicate = False
    async with ctx.matchmaking_manager.lock:
        try:
            ctx.matchmaking_manager.add_player(entry)
        except ValueError:
            duplicate = True
        else:
            position = ctx.matchmaking_manager.queue_size
            matched = ctx.matchmaking_manager.try_match()

    # Lock released -- handle duplicate rejection outside lock
    if duplicate:
        log.info("matchmaking rejected", reason="already_in_queue")
        await websocket.send_json({"type": "error", "message": "already_in_queue"})
        await websocket.close(code=4000, reason="already_in_queue")
        return False

    if matched:
        log.info("match found", players=[e.username for e in matched])
        await _handle_match(matched, ctx)
        # True if re-queued after match failure, False if game created successfully
        return ctx.matchmaking_manager.has_user(ctx.user_id)

    await websocket.send_json({"type": "queue_joined", "position": position, "queue_size": position})
    log.info("player queued", queue_size=position)
    # Broadcast queue update to other waiting players (exclude self, already got queue_joined)
    await _broadcast_queue_update(ctx, exclude=ctx.connection_id)
    return True


async def _message_loop(websocket: WebSocket) -> None:
    while True:
        raw = await websocket.receive_text()
        try:
            message = parse_matchmaking_message(raw)
        except ValidationError:
            await websocket.send_json({"type": "error", "message": "Invalid message format"})
            continue
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "message": "Invalid JSON"})
            continue
        except ValueError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            continue

        if isinstance(message, MatchmakingPingMessage):
            await websocket.send_json({"type": "pong"})


async def _handle_match(matched: list[QueueEntry], ctx: _MatchmakingContext) -> None:
    """Create a game for matched players and send game_starting to each."""
    game_id = str(uuid.uuid4())
    log = logger.bind(game_id=game_id)

    # Verify all players are still connected before creating the game
    if any(e.websocket.client_state != WebSocketState.CONNECTED for e in matched):
        async with ctx.matchmaking_manager.lock:
            # Re-check under lock to avoid requeuing players who disconnected
            # between the check above and lock acquisition (TOCTOU)
            remaining = [e for e in matched if e.websocket.client_state == WebSocketState.CONNECTED]
            disconnected = [e for e in matched if e.websocket.client_state != WebSocketState.CONNECTED]
            ctx.matchmaking_manager.requeue_at_front(remaining)
            ctx.matchmaking_manager.clear_in_flight({e.user_id for e in disconnected})
        log.warning(
            "matched players disconnected before game creation",
            disconnected=[e.username for e in disconnected],
        )
        if remaining:
            await _broadcast_queue_update(ctx)
        return

    # Sign tickets and create game -- catch any exception to avoid leaking _in_flight
    try:
        players_for_tickets = [(entry.user_id, entry.username, entry.connection_id) for entry in matched]
        player_specs, ticket_map = sign_player_tickets(
            players_for_tickets,
            game_id,
            ctx.auth_settings.game_ticket_secret,
        )
        ws_url = await create_game_on_server(
            game_id,
            player_specs,
            0,  # matchmaking always has 0 AI players
            ctx.registry,
        )
    except Exception:
        log.exception("failed to create game from matchmaking")
        async with ctx.matchmaking_manager.lock:
            # Check connection state under lock to avoid requeuing
            # players who disconnected before lock acquisition (TOCTOU)
            connected = [e for e in matched if e.websocket.client_state == WebSocketState.CONNECTED]
            disconnected = [e for e in matched if e.websocket.client_state != WebSocketState.CONNECTED]
            ctx.matchmaking_manager.requeue_at_front(connected)
            ctx.matchmaking_manager.clear_in_flight({e.user_id for e in disconnected})
        for entry in connected:
            with contextlib.suppress(WebSocketDisconnect, ConnectionError, RuntimeError):
                await entry.websocket.send_json(
                    {"type": "error", "message": "Failed to start game, please try again"},
                )
        await _broadcast_queue_update(ctx)
        return

    game_client_url = ctx.settings.game_client_url
    log.info("game created from matchmaking", ws_url=ws_url)

    async with ctx.matchmaking_manager.lock:
        ctx.matchmaking_manager.clear_in_flight({e.user_id for e in matched})

    # Send game_starting to each player and close their connections
    for entry in matched:
        ticket = ticket_map.get(entry.connection_id, "")
        try:
            await entry.websocket.send_json(
                {
                    "type": "game_starting",
                    "ws_url": ws_url,
                    "game_ticket": ticket,
                    "game_id": game_id,
                    "game_client_url": game_client_url,
                },
            )
            await entry.websocket.close()
        except WebSocketDisconnect, ConnectionError, RuntimeError:  # pragma: no cover
            log.warning("failed to send game_starting", connection_id=entry.connection_id)


async def _broadcast_queue_update(ctx: _MatchmakingContext, *, exclude: str | None = None) -> None:
    """Send queue_update to all players currently in the queue."""
    async with ctx.matchmaking_manager.lock:
        queue_size = ctx.matchmaking_manager.queue_size
        entries = ctx.matchmaking_manager.get_queue_entries()

    for entry in entries:
        if entry.connection_id == exclude:
            continue
        if entry.websocket.client_state == WebSocketState.CONNECTED:
            with contextlib.suppress(WebSocketDisconnect, ConnectionError, RuntimeError):
                await entry.websocket.send_json({"type": "queue_update", "queue_size": queue_size})


async def _cleanup_connection(ctx: _MatchmakingContext) -> None:
    """Remove player from queue on disconnect."""
    async with ctx.matchmaking_manager.lock:
        ctx.matchmaking_manager.remove_player(ctx.connection_id)

    logger.info("player left matchmaking queue", username=ctx.username)
    await _broadcast_queue_update(ctx)
