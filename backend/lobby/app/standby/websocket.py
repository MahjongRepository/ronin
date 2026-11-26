from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.dal.models import AccountType
from app.game_transition import hand_back_live_game
from app.occupancy import ALREADY_IN_GAME, REPLACED_BY_NEW_CONNECTION
from app.websocket_utils import serve_lobby_socket

if TYPE_CHECKING:
    import httpx
    from starlette.websockets import WebSocket

    from app.bot_pool import BotPool
    from app.occupancy import Occupancy, RejectionMessage
    from app.players import LobbyPlayer
    from app.settings import LobbyServerSettings

logger = structlog.get_logger()

_BOT_ACCOUNT_REQUIRED = "bot_account_required"


class _StandbyContext:
    """
    Bundles per-connection state extracted from app.state.
    """

    __slots__ = (
        "bot_pool",
        "game_server",
        "occupancy",
        "settings",
    )

    def __init__(self, websocket: WebSocket) -> None:
        self.settings: LobbyServerSettings = websocket.app.state.settings
        self.game_server: httpx.AsyncClient = websocket.app.state.game_server
        self.bot_pool: BotPool = websocket.app.state.bot_pool
        self.occupancy: Occupancy = websocket.app.state.occupancy


async def standby_websocket(websocket: WebSocket) -> None:
    """
    Handle a bot account's WebSocket connection standing by for a room's open seat.
    """
    ctx = _StandbyContext(websocket)
    await serve_lobby_socket(
        websocket, lambda player: _serve_bot(player, ctx, account_type=websocket.user.account_type)
    )


async def _serve_bot(player: LobbyPlayer, ctx: _StandbyContext, *, account_type: AccountType) -> None:
    """
    Stand the bot by and wait for its socket to end; it leaves the pool whatever happens.

    A human account is refused: its API token passes the key check, so the account type is the gate. An unexpected
    error is not caught here: it propagates to the ASGI server, which logs it, after the cleanup ran.
    """
    if account_type != AccountType.BOT:
        _send_error_and_close(player, {"type": "error", "message": _BOT_ACCOUNT_REQUIRED})
        return

    try:
        if await _try_stand_by(player, ctx):
            await _message_loop(player)
    except ConnectionError:
        pass
    finally:
        _cleanup_connection(player, ctx)


async def _try_stand_by(player: LobbyPlayer, ctx: _StandbyContext) -> bool:
    """
    Attempt to put the bot on standby; return True if it stands by and should enter the message loop.

    A refusal as ``already_in_game``, from the game lookup or from a start that handed the bot to a game while that
    lookup was in flight, is answered with the bot's live game when the game server names it, so its wait ends with its
    ticket rather than an error. Any other refusal is told and closed.
    """
    log = logger.bind(username=player.username, connection_id=player.connection_id)

    joined = await _admit(player, ctx)
    if joined == ALREADY_IN_GAME and await hand_back_live_game(
        player, settings=ctx.settings, game_server=ctx.game_server
    ):
        return False

    if isinstance(joined, str):
        log.info("standby rejected", reason=joined)
        _send_error_and_close(player, ctx.occupancy.rejection_message(player.user_id, joined))
        return False

    player.send({"type": "standby_joined"})
    if joined is not None:
        _send_error_and_close(joined, {"type": "error", "message": REPLACED_BY_NEW_CONNECTION})
        log.info("standby entry taken over by a new connection")
        return True

    log.info("bot standing by")
    return True


async def _admit(player: LobbyPlayer, ctx: _StandbyContext) -> LobbyPlayer | str | None:
    """
    Stand the bot by under the occupancy rule; return the connection whose entry it took over, the rejection, or None.
    """
    with ctx.occupancy.admitting(player.user_id):
        game_conflict = await ctx.occupancy.find_game_conflict(player.user_id)
        if game_conflict is not None:
            return game_conflict

        try:
            displaced = ctx.bot_pool.add(player)
        except ValueError as e:
            return str(e)

        ctx.occupancy.release_held_seat(player.user_id)
        return displaced


async def _message_loop(player: LobbyPlayer) -> None:
    """
    Wait for the client's disconnect; the client sends nothing, so any frame it does send is discarded unanswered.
    """
    while True:
        await player.connection.receive()


def _send_error_and_close(player: LobbyPlayer, error: RejectionMessage) -> None:
    """
    Tell the client why its standby ended and close with 4000, the reason as the close reason.
    """
    player.send(error)
    player.connection.close(code=4000, reason=error["message"])


def _cleanup_connection(player: LobbyPlayer, ctx: _StandbyContext) -> None:
    """
    Remove the bot's idle entry once the socket ends; a claimed or taken-over connection changes nothing.
    """
    if ctx.bot_pool.remove(player.connection_id):
        logger.info("bot left standby", username=player.username)
