from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import structlog
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketDisconnected, WebSocketState

from lobby.game_transition import create_game_on_server, sign_player_tickets
from lobby.matchmaking.models import QueueEntry
from lobby.websocket_utils import check_origin, close_quietly, send_or_drop

if TYPE_CHECKING:
    from lobby.matchmaking.manager import MatchmakingManager
    from lobby.occupancy import Occupancy
    from lobby.registry.manager import RegistryManager
    from lobby.settings import LobbyServerSettings
    from shared.auth.settings import AuthSettings

logger = structlog.get_logger()

_MATCH_FAILED = "match_failed"


class _MatchmakingContext:
    """
    Bundles per-connection state extracted from app.state.
    """

    __slots__ = (
        "auth_settings",
        "connection_id",
        "matchmaking_manager",
        "occupancy",
        "registry",
        "settings",
        "user_id",
        "username",
    )

    def __init__(self, websocket: WebSocket) -> None:
        self.settings: LobbyServerSettings = websocket.app.state.settings
        self.auth_settings: AuthSettings = websocket.app.state.auth_settings
        self.matchmaking_manager: MatchmakingManager = websocket.app.state.matchmaking_manager
        self.registry: RegistryManager = websocket.app.state.registry
        self.occupancy: Occupancy = websocket.app.state.occupancy

        self.connection_id: str = str(uuid.uuid4())
        self.user_id: str = websocket.user.user_id
        self.username: str = websocket.user.username


async def matchmaking_websocket(websocket: WebSocket) -> None:
    """
    Handle a WebSocket connection for matchmaking.

    ``WebSocketDisconnected`` is a normal end too: it is what the next receive raises once another task (the handler
    that resolved this player's match) closed this socket while the handler was not waiting on a receive.
    """
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
    except WebSocketDisconnect, WebSocketDisconnected:
        pass
    except Exception:  # pragma: no cover -- defensive catch-all
        logger.exception("unexpected error in matchmaking websocket")
    finally:
        await _cleanup_connection(ctx)


async def _try_join_queue(websocket: WebSocket, ctx: _MatchmakingContext) -> bool:
    """
    Attempt to join the matchmaking queue.

    Return True if the player is queued and should enter the message loop. Return False if the connection was rejected
    or this join completed a match, whether its game was created or not: either way the socket is closed. The check that
    the user is not playing a game, which asks the game servers, runs before the lock; ``add_player`` checks the rest of
    the occupancy rule under it, including a start that handed the user to a game while that lookup was in flight.
    """
    log = logger.bind(username=ctx.username, connection_id=ctx.connection_id)

    entry = QueueEntry(
        connection_id=ctx.connection_id,
        user_id=ctx.user_id,
        username=ctx.username,
        websocket=websocket,
    )

    matched = None
    position = 0
    with ctx.occupancy.admitting(ctx.user_id):
        rejection = await ctx.occupancy.find_game_conflict(ctx.user_id)
        if rejection is None:
            async with ctx.matchmaking_manager.lock:
                try:
                    ctx.matchmaking_manager.add_player(entry)
                except ValueError as e:
                    rejection = str(e)
                else:
                    position = ctx.matchmaking_manager.queue_size
                    matched = ctx.matchmaking_manager.try_match()

    if rejection is not None:
        log.info("matchmaking rejected", reason=rejection)
        await _send_error_and_close(websocket, reason=rejection)
        return False

    if matched:
        log.info("match found", players=[e.username for e in matched])
        await _handle_match(matched, ctx)
        return False

    await websocket.send_json({"type": "queue_joined", "position": position, "queue_size": position})
    log.info("player queued", queue_size=position)
    # Broadcast queue update to other waiting players (exclude self, already got queue_joined)
    await _broadcast_queue_update(ctx, exclude=ctx.connection_id)
    return True


async def _message_loop(websocket: WebSocket) -> None:
    """
    Wait for the client's disconnect; the client sends nothing, so any frame it does send is discarded unanswered.
    """
    while (await websocket.receive())["type"] != "websocket.disconnect":
        pass


async def _send_error_and_close(websocket: WebSocket, *, reason: str) -> None:
    """
    Tell the client why matchmaking ended for it and close with 4000; a peer that is already gone is skipped.
    """
    await send_or_drop(websocket, json.dumps({"type": "error", "message": reason}))
    await close_quietly(websocket, code=4000, reason=reason)


async def _handle_match(matched: list[QueueEntry], ctx: _MatchmakingContext) -> None:
    """
    Create a game for the matched players, then send each of them ``game_starting`` and close their sockets.

    The four are released (neither queued nor in flight) whatever the outcome. A failed creation is terminal: each of
    them gets ``match_failed`` and a 4000 close, and rejoins on its own. It is never retried, because a failure may mean
    the game exists. A player who disconnected meanwhile keeps the seat: the game server replaces a seat nobody joins
    with AI.
    """
    game_id = str(uuid.uuid4())
    log = logger.bind(game_id=game_id)

    try:
        created = await _create_game(matched, ctx, game_id=game_id)
    except Exception:
        log.exception("failed to create game from matchmaking")
        created = None
    finally:
        async with ctx.matchmaking_manager.lock:
            ctx.matchmaking_manager.clear_in_flight({e.user_id for e in matched})

    if created is None:
        for entry in matched:
            await _send_error_and_close(entry.websocket, reason=_MATCH_FAILED)
        return

    ws_url, ticket_map = created
    log.info("game created from matchmaking", ws_url=ws_url)
    for entry in matched:
        delivered = await send_or_drop(
            entry.websocket,
            json.dumps(
                {
                    "type": "game_starting",
                    "ws_url": ws_url,
                    "game_ticket": ticket_map[entry.connection_id],
                    "game_id": game_id,
                    "game_client_url": ctx.settings.game_client_url,
                },
            ),
        )
        if not delivered:
            log.warning("failed to deliver game_starting", connection_id=entry.connection_id)
        await close_quietly(entry.websocket)


async def _create_game(
    matched: list[QueueEntry],
    ctx: _MatchmakingContext,
    *,
    game_id: str,
) -> tuple[str, dict[str, str]]:
    """
    Sign a ticket per matched player and create the game; return the game server URL and the tickets by connection.

    The attempt hands the matched users to the game whatever its outcome, before the caller releases them from the
    in-flight set: a failure may mean the game server created the game anyway.
    """
    players_for_tickets = [(entry.user_id, entry.username, entry.connection_id) for entry in matched]
    player_specs, ticket_map = sign_player_tickets(
        players=players_for_tickets,
        game_id=game_id,
        ticket_secret=ctx.auth_settings.game_ticket_secret,
    )
    try:
        ws_url = await create_game_on_server(
            game_id=game_id,
            players=player_specs,
            num_ai_players=0,
            registry=ctx.registry,
        )
    finally:
        ctx.occupancy.hand_to_game(entry.user_id for entry in matched)

    return ws_url, ticket_map


async def _broadcast_queue_update(ctx: _MatchmakingContext, *, exclude: str | None = None) -> None:
    """
    Send queue_update to all players currently in the queue.
    """

    async with ctx.matchmaking_manager.lock:
        queue_size = ctx.matchmaking_manager.queue_size
        entries = ctx.matchmaking_manager.get_queue_entries()

    message = json.dumps({"type": "queue_update", "queue_size": queue_size})
    for entry in entries:
        if entry.connection_id != exclude and entry.websocket.client_state == WebSocketState.CONNECTED:
            await send_or_drop(entry.websocket, message)


async def _cleanup_connection(ctx: _MatchmakingContext) -> None:
    """
    Remove player from queue on disconnect.
    """

    async with ctx.matchmaking_manager.lock:
        ctx.matchmaking_manager.remove_player(ctx.connection_id)

    logger.info("player left matchmaking queue", username=ctx.username)
    await _broadcast_queue_update(ctx)
