from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import structlog

from lobby.game_transition import create_game_on_server, sign_player_tickets
from lobby.players import LobbyPlayer
from lobby.websocket_utils import check_origin
from shared.websocket import QueuedWebSocket, accept_websocket, reject_websocket

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from lobby.matchmaking.manager import MatchmakingManager
    from lobby.occupancy import Occupancy
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
        "matchmaking_manager",
        "occupancy",
        "settings",
    )

    def __init__(self, websocket: WebSocket) -> None:
        self.settings: LobbyServerSettings = websocket.app.state.settings
        self.auth_settings: AuthSettings = websocket.app.state.auth_settings
        self.matchmaking_manager: MatchmakingManager = websocket.app.state.matchmaking_manager
        self.occupancy: Occupancy = websocket.app.state.occupancy


async def matchmaking_websocket(websocket: WebSocket) -> None:
    """
    Handle a WebSocket connection for matchmaking; this task owns the connection's writer.
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
        await _serve_player(player, _MatchmakingContext(websocket))
    finally:
        await player.connection.stop_writer()


async def _serve_player(player: LobbyPlayer, ctx: _MatchmakingContext) -> None:
    """
    Queue the player and wait for their socket to end; they leave the queue whatever happens.
    """
    try:
        if await _try_join_queue(player, ctx):
            await _message_loop(player)
    except ConnectionError:
        pass
    except Exception:  # pragma: no cover -- defensive catch-all
        logger.exception("unexpected error in matchmaking websocket")
    finally:
        _cleanup_connection(player, ctx)


async def _try_join_queue(player: LobbyPlayer, ctx: _MatchmakingContext) -> bool:
    """
    Attempt to join the matchmaking queue.

    Return True if the player is queued and should enter the message loop. Return False if the connection was rejected
    or this join completed a match, whether its game was created or not: either way the socket is closed. The check that
    the user is not playing a game, which asks the game server, runs first; ``add_player`` then checks the rest of the
    occupancy rule in the same synchronous step that queues the user, including a start that handed the user to a game
    while that lookup was in flight.
    """
    log = logger.bind(username=player.username, connection_id=player.connection_id)

    matched = None
    position = 0
    with ctx.occupancy.admitting(player.user_id):
        rejection = await ctx.occupancy.find_game_conflict(player.user_id)
        if rejection is None:
            try:
                ctx.matchmaking_manager.add_player(player)
            except ValueError as e:
                rejection = str(e)
            else:
                position = ctx.matchmaking_manager.queue_size
                matched = ctx.matchmaking_manager.try_match()

    if rejection is not None:
        log.info("matchmaking rejected", reason=rejection)
        _send_error_and_close(player, reason=rejection)
        return False

    if matched:
        log.info("match found", players=[p.username for p in matched])
        await _handle_match(matched, ctx)
        return False

    player.send({"type": "queue_joined", "position": position, "queue_size": position})
    log.info("player queued", queue_size=position)
    _broadcast_queue_update(ctx, exclude=player.connection_id)
    return True


async def _message_loop(player: LobbyPlayer) -> None:
    """
    Wait for the client's disconnect; the client sends nothing, so any frame it does send is discarded unanswered.
    """
    while True:
        await player.connection.receive()


def _send_error_and_close(player: LobbyPlayer, *, reason: str) -> None:
    """
    Tell the client why matchmaking ended for it and close with 4000.
    """
    player.send({"type": "error", "message": reason})
    player.connection.close(code=4000, reason=reason)


async def _handle_match(matched: list[LobbyPlayer], ctx: _MatchmakingContext) -> None:
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
        ctx.matchmaking_manager.clear_in_flight({p.user_id for p in matched})

    if created is None:
        for player in matched:
            _send_error_and_close(player, reason=_MATCH_FAILED)
        return

    ws_url, ticket_map = created
    log.info("game created from matchmaking", ws_url=ws_url)
    for player in matched:
        player.send(
            {
                "type": "game_starting",
                "ws_url": ws_url,
                "game_ticket": ticket_map[player.connection_id],
                "game_id": game_id,
                "game_client_url": ctx.settings.game_client_url,
            },
        )
        player.connection.close()


async def _create_game(
    matched: list[LobbyPlayer],
    ctx: _MatchmakingContext,
    *,
    game_id: str,
) -> tuple[str, dict[str, str]]:
    """
    Sign a ticket per matched player and create the game; return the game server URL and the tickets by connection.

    The attempt hands the matched users to the game whatever its outcome, before the caller releases them from the
    in-flight set: a failure may mean the game server created the game anyway.
    """
    players_for_tickets = [(p.user_id, p.username, p.connection_id) for p in matched]
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
            settings=ctx.settings,
        )
    finally:
        ctx.occupancy.hand_to_game(p.user_id for p in matched)

    return ws_url, ticket_map


def _broadcast_queue_update(ctx: _MatchmakingContext, *, exclude: str | None = None) -> None:
    """
    Send queue_update to all players currently in the queue.
    """
    queued = ctx.matchmaking_manager.get_queued_players()
    payload = json.dumps({"type": "queue_update", "queue_size": len(queued)})
    for player in queued:
        if player.connection_id != exclude:
            player.connection.send_text(payload)


def _cleanup_connection(player: LobbyPlayer, ctx: _MatchmakingContext) -> None:
    """
    Remove player from queue on disconnect.
    """
    ctx.matchmaking_manager.remove_player(player.connection_id)
    logger.info("player left matchmaking queue", username=player.username)
    _broadcast_queue_update(ctx)
