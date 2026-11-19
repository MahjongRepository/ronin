from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from lobby.websocket_utils import serve_lobby_socket

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from lobby.live_games.feed import PlayingGamesFeed
    from lobby.players import LobbyPlayer

logger = structlog.get_logger()


async def playing_games_websocket(websocket: WebSocket) -> None:
    """
    Handle the lobby page's send-only socket of the games being played.
    """
    feed: PlayingGamesFeed = websocket.app.state.playing_games_feed
    await serve_lobby_socket(websocket, lambda watcher: _serve_watcher(watcher, feed))


async def _serve_watcher(watcher: LobbyPlayer, feed: PlayingGamesFeed) -> None:
    """
    Send the watcher the list of games being played and its every change until the socket ends; whatever the client
    sends is read and dropped.
    """
    feed.watch(watcher)
    try:
        while True:
            await watcher.connection.receive()
    except ConnectionError:
        pass
    except Exception:
        logger.exception("unexpected error in playing games websocket", username=watcher.username)
    finally:
        feed.unwatch(watcher)
