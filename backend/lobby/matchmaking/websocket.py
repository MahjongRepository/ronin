from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from lobby.game_transition import GameStartError, hand_back_live_game, start_game
from lobby.occupancy import ALREADY_IN_GAME, REPLACED_BY_NEW_CONNECTION
from lobby.websocket_utils import serve_lobby_socket

if TYPE_CHECKING:
    import httpx
    from starlette.websockets import WebSocket

    from lobby.matchmaking.manager import MatchmakingManager, QueuePlace
    from lobby.occupancy import Occupancy, RejectionMessage
    from lobby.players import LobbyPlayer
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
        "game_server",
        "matchmaking_manager",
        "occupancy",
        "settings",
    )

    def __init__(self, websocket: WebSocket) -> None:
        self.settings: LobbyServerSettings = websocket.app.state.settings
        self.auth_settings: AuthSettings = websocket.app.state.auth_settings
        self.game_server: httpx.AsyncClient = websocket.app.state.game_server
        self.matchmaking_manager: MatchmakingManager = websocket.app.state.matchmaking_manager
        self.occupancy: Occupancy = websocket.app.state.occupancy


async def matchmaking_websocket(websocket: WebSocket) -> None:
    """
    Handle a WebSocket connection for matchmaking.
    """
    ctx = _MatchmakingContext(websocket)
    await serve_lobby_socket(websocket, lambda player: _serve_player(player, ctx))


async def _serve_player(player: LobbyPlayer, ctx: _MatchmakingContext) -> None:
    """
    Queue the player and wait for their socket to end; they leave the queue whatever happens.

    An unexpected error is not caught here: it propagates to the ASGI server, which logs it, after the cleanup ran.
    """
    try:
        if await _try_join_queue(player, ctx):
            await _message_loop(player)
    except ConnectionError:
        pass
    finally:
        _cleanup_connection(player, ctx)


async def _try_join_queue(player: LobbyPlayer, ctx: _MatchmakingContext) -> bool:
    """
    Attempt to join the matchmaking queue.

    Return True if the player is queued, in a new entry or in the user's own entry taken over from their older
    connection, and should enter the message loop. Return False if the connection was rejected or this join completed a
    match, whether its game was created or not: either way the socket is closed. The check that the user is not playing
    a game, which asks the game server, runs first; ``add_player`` then checks the rest of the occupancy rule in the
    same synchronous step that queues the user, including a start that handed the user to a game while that lookup was
    in flight.
    """
    log = logger.bind(username=player.username, connection_id=player.connection_id)

    joined = await _admit(player, ctx)
    if joined == ALREADY_IN_GAME and await hand_back_live_game(
        player, settings=ctx.settings, game_server=ctx.game_server
    ):
        return False

    if isinstance(joined, str):
        log.info("matchmaking rejected", reason=joined)
        _send_error_and_close(player, ctx.occupancy.rejection_message(player.user_id, joined))
        return False

    if isinstance(joined, list):
        log.info("match found", players=[p.username for p in joined])
        await _handle_match(joined, ctx)
        return False

    player.send({"type": "queue_joined", "position": joined.position, "queue_size": ctx.matchmaking_manager.queue_size})
    if joined.displaced is not None:
        _send_error_and_close(joined.displaced, {"type": "error", "message": REPLACED_BY_NEW_CONNECTION})
        log.info("queue entry taken over by a new connection", position=joined.position)
        return True

    log.info("player queued", queue_size=joined.position)
    _broadcast_queue_update(ctx, exclude=player.connection_id)
    return True


async def _admit(player: LobbyPlayer, ctx: _MatchmakingContext) -> QueuePlace | list[LobbyPlayer] | str:
    """
    Queue the player under the occupancy rule; return their queue place, the matched players, or the rejection.
    """
    with ctx.occupancy.admitting(player.user_id):
        game_conflict = await ctx.occupancy.find_game_conflict(player.user_id)
        if game_conflict is not None:
            return game_conflict

        try:
            return ctx.matchmaking_manager.add_player(player)
        except ValueError as e:
            return str(e)


async def _message_loop(player: LobbyPlayer) -> None:
    """
    Wait for the client's disconnect; the client sends nothing, so any frame it does send is discarded unanswered.
    """
    while True:
        await player.connection.receive()


def _send_error_and_close(player: LobbyPlayer, error: RejectionMessage) -> None:
    """
    Tell the client why matchmaking ended for it and close with 4000, the reason as the close reason.
    """
    player.send(error)
    player.connection.close(code=4000, reason=error["message"])


async def _handle_match(matched: list[LobbyPlayer], ctx: _MatchmakingContext) -> None:
    """
    Start a game for the matched players.

    The four are released (neither queued nor in flight) whatever the outcome. A failed creation is terminal: each of
    them gets ``match_failed`` and a 4000 close, and rejoins on its own. It is never retried, because a failure may mean
    the game exists. A player who disconnected meanwhile keeps the seat: the game server replaces a seat nobody joins
    with AI.
    """
    try:
        game_id = await start_game(
            matched,
            num_ai_players=0,
            settings=ctx.settings,
            ticket_secret=ctx.auth_settings.game_ticket_secret,
            occupancy=ctx.occupancy,
            game_server=ctx.game_server,
        )
    except GameStartError:
        for player in matched:
            _send_error_and_close(player, {"type": "error", "message": _MATCH_FAILED})
        return
    finally:
        ctx.matchmaking_manager.clear_in_flight({player.user_id for player in matched})

    logger.info("game created from matchmaking", game_id=game_id)


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
    Remove the player's queue entry once the socket ends and tell the rest of the queue.

    A connection that holds no entry (rejected, matched, or taken over by the user's newer one) changes nothing, so
    nothing is logged or sent.
    """
    if not ctx.matchmaking_manager.remove_player(player.connection_id):
        return

    logger.info("player left matchmaking queue", username=player.username)
    _broadcast_queue_update(ctx)
