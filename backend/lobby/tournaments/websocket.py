from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog
from pydantic import ValidationError

from lobby.occupancy import REPLACED_BY_NEW_CONNECTION
from lobby.tournaments.messages import TournamentClientMessage, parse_tournament_message
from lobby.websocket_utils import serve_lobby_socket
from shared.rate_limit import TokenBucket

if TYPE_CHECKING:
    from starlette.types import Message
    from starlette.websockets import WebSocket

    from lobby.players import LobbyPlayer
    from lobby.tournaments.hub import TournamentHub
    from shared.dal.tournament_repository import TournamentRepository

logger = structlog.get_logger()

_RATE_LIMIT_RATE = 5.0
_RATE_LIMIT_BURST = 10
_RATE_LIMITED = "rate_limited"
_BINARY_FRAME = "Binary frames are not supported"
_TOURNAMENT_NOT_FOUND = "tournament_not_found"


class _TournamentContext:
    """
    Bundles per-connection state extracted from app.state.
    """

    __slots__ = ("hub", "tournament_id", "tournament_repo")

    def __init__(self, websocket: WebSocket) -> None:
        self.tournament_id: str = websocket.path_params["tournament_id"]
        self.hub: TournamentHub = websocket.app.state.tournament_hub
        self.tournament_repo: TournamentRepository = websocket.app.state.tournament_repo


async def tournament_websocket(websocket: WebSocket) -> None:
    """
    Handle a player's WebSocket connection on a tournament page.
    """
    ctx = _TournamentContext(websocket)
    await serve_lobby_socket(websocket, lambda player: _serve_player(player, ctx))


async def tournament_events_websocket(websocket: WebSocket) -> None:
    """
    Handle the owner's events socket of a tournament: send-only, never online, several per owner allowed.
    """
    ctx = _TournamentContext(websocket)
    await serve_lobby_socket(websocket, lambda subscriber: _serve_subscriber(subscriber, ctx))


async def _serve_subscriber(subscriber: LobbyPlayer, ctx: _TournamentContext) -> None:
    """
    Subscribe the tournament's owner to its events, starting with a ``presence`` snapshot, until the socket ends.

    Anyone else is refused as for an unknown tournament; whatever the client sends is read and dropped.
    """
    tournament = await ctx.tournament_repo.get_tournament(ctx.tournament_id)
    if tournament is None or tournament.owner_user_id != subscriber.user_id:
        logger.info("tournament events rejected", tournament_id=ctx.tournament_id, username=subscriber.username)
        subscriber.send({"type": "error", "message": _TOURNAMENT_NOT_FOUND})
        subscriber.connection.close(code=4000, reason=_TOURNAMENT_NOT_FOUND)
        return

    ctx.hub.subscribe(ctx.tournament_id, subscriber)
    subscriber.send(ctx.hub.presence(ctx.tournament_id))
    try:
        while True:
            await subscriber.connection.receive()
    except ConnectionError:
        pass
    except Exception:
        logger.exception("unexpected error in tournament events websocket", tournament_id=ctx.tournament_id)
    finally:
        ctx.hub.unsubscribe(ctx.tournament_id, subscriber)


async def _serve_player(player: LobbyPlayer, ctx: _TournamentContext) -> None:
    """
    Put the player online and serve their chat until the socket ends; then take them offline, whatever happened.
    """
    try:
        if await _join(player, ctx):
            await _message_loop(player, ctx)
    except ConnectionError:
        pass
    except Exception:
        logger.exception(
            "unexpected error in tournament websocket", tournament_id=ctx.tournament_id, username=player.username
        )
    finally:
        _leave(player, ctx)


async def _join(player: LobbyPlayer, ctx: _TournamentContext) -> bool:
    """
    Put the player online, send them the kept chat history if any, then acknowledge it and announce it; return False
    when the tournament does not exist.

    The same user's older connection is told ``replaced_by_new_connection`` and closed; the new one takes its place.
    """
    if await ctx.tournament_repo.get_tournament(ctx.tournament_id) is None:
        logger.info("tournament join rejected", tournament_id=ctx.tournament_id, username=player.username)
        player.send({"type": "error", "message": _TOURNAMENT_NOT_FOUND})
        player.connection.close(code=4000, reason=_TOURNAMENT_NOT_FOUND)
        return False

    replaced = ctx.hub.connect(ctx.tournament_id, player)
    if replaced is not None:
        replaced.send({"type": "error", "message": REPLACED_BY_NEW_CONNECTION})
        replaced.connection.close(code=4000, reason=REPLACED_BY_NEW_CONNECTION)

    history = ctx.hub.chat_history(ctx.tournament_id)
    if history:
        player.send({"type": "chat_history", "messages": history})
    names = ctx.hub.online_names(ctx.tournament_id)
    player.send({"type": "joined", "players": names})
    ctx.hub.broadcast_presence(ctx.tournament_id, exclude=player.connection_id)
    logger.info("player online in tournament", tournament_id=ctx.tournament_id, username=player.username)
    return True


async def _message_loop(player: LobbyPlayer, ctx: _TournamentContext) -> None:
    """
    Keep each chat line of the player in the tournament's history and broadcast it to the whole tournament, its sender
    included, until the socket ends.
    """
    bucket = TokenBucket(rate=_RATE_LIMIT_RATE, burst=_RATE_LIMIT_BURST)
    while True:
        message = _read_message(player, bucket=bucket, frame=await player.connection.receive())
        if message is not None:
            ctx.hub.add_chat_line(ctx.tournament_id, player.username, message.text)
            ctx.hub.broadcast(ctx.tournament_id, {"type": "chat", "player_name": player.username, "text": message.text})


def _read_message(player: LobbyPlayer, *, bucket: TokenBucket, frame: Message) -> TournamentClientMessage | None:
    """
    Return the frame's tournament message, or None after answering the error that rejected it.

    Every frame counts against the player's rate limit before it is read, as on the room socket, with the same errors.
    """
    if not bucket.consume():
        player.send({"type": "error", "message": _RATE_LIMITED})
        return None

    text = frame.get("text")
    if text is None:
        player.send({"type": "error", "message": _BINARY_FRAME})
        return None

    try:
        return parse_tournament_message(text)
    except json.JSONDecodeError:
        player.send({"type": "error", "message": "Invalid JSON"})
    except ValidationError:
        player.send({"type": "error", "message": "Invalid message"})
    except ValueError:
        player.send({"type": "error", "message": "Message too large"})

    return None


def _leave(player: LobbyPlayer, ctx: _TournamentContext) -> None:
    """
    Take the player offline and tell the rest; a connection another one replaced leaves nothing to announce.
    """
    if not ctx.hub.disconnect(ctx.tournament_id, player):
        return

    logger.info(
        "player offline in tournament",
        tournament_id=ctx.tournament_id,
        username=player.username,
        close_code=player.connection.disconnect_code,
    )
    ctx.hub.broadcast_presence(ctx.tournament_id)
