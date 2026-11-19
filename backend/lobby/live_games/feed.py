from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import structlog

from lobby.game_transition import GameListError
from shared.tasks import cancel_and_wait

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from lobby.game_transition import PlayingGame
    from lobby.players import LobbyPlayer

logger = structlog.get_logger()

PLAYING_GAMES = "games"


class PlayingGamesFeed:
    """
    The games the game server plays, pushed to every lobby page that watches them.

    The game server never calls the lobby, so one task polls its list every interval while anyone watches, and sends
    every watcher the whole list, encoded once, whenever it changes. A new watcher gets the last list at once; with none
    kept (nobody watched since the last watcher left), the next poll sends it. A failed poll keeps the last list and is
    logged once until a poll succeeds again. Every method but the poll is one synchronous step on the event loop, so no
    lock is needed.
    """

    def __init__(
        self,
        *,
        fetch: Callable[[], Awaitable[tuple[PlayingGame, ...]]],
        interval_seconds: float,
    ) -> None:
        self._fetch = fetch
        self._interval_seconds = interval_seconds
        self._watchers: dict[str, LobbyPlayer] = {}
        self._watched = asyncio.Event()
        self._games: tuple[PlayingGame, ...] | None = None
        self._failing = False
        self._task: asyncio.Task[None] | None = None

    def watch(self, watcher: LobbyPlayer) -> None:
        """
        Send the watcher every change of the list from now on, starting with the list kept, if any.
        """
        self._watchers[watcher.connection_id] = watcher
        self._watched.set()
        if self._games is not None:
            watcher.connection.send_text(_encode(self._games))

    def unwatch(self, watcher: LobbyPlayer) -> None:
        """
        Stop sending to the watcher; once nobody watches, stop polling and forget the list.
        """
        self._watchers.pop(watcher.connection_id, None)
        if not self._watchers:
            self._watched.clear()
            self._games = None

    def start(self) -> None:
        """
        Start the polling task.
        """
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """
        Cancel the polling task.
        """
        if self._task is not None:
            await cancel_and_wait([self._task])
            self._task = None

    async def poll_once(self) -> None:
        """
        Fetch the list and send it to every watcher when it changed; a list fetched after the last watcher left is
        dropped.
        """
        try:
            games = await self._fetch()
        except GameListError as e:
            if not self._failing:
                logger.warning("playing games lookup failed, keeping the last list", error=str(e))

            self._failing = True
            return

        if self._failing:
            logger.info("playing games lookup recovered")

        self._failing = False
        if not self._watchers or games == self._games:
            return

        self._games = games
        payload = _encode(games)
        for watcher in self._watchers.values():
            watcher.connection.send_text(payload)

    async def _poll_loop(self) -> None:
        """
        Run a poll every interval while anyone watches; a failed poll is logged and the next one still runs.
        """
        while True:
            await self._watched.wait()
            try:
                await self.poll_once()
            except Exception:
                logger.exception("playing games poll failed")

            await asyncio.sleep(self._interval_seconds)


def _encode(games: tuple[PlayingGame, ...]) -> str:
    return json.dumps({"type": PLAYING_GAMES, "games": [game.model_dump(mode="json") for game in games]})
