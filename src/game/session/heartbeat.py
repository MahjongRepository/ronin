"""Monitor client liveness via application-level heartbeat."""

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from game.session.models import Game

HEARTBEAT_CHECK_INTERVAL = 5  # seconds between heartbeat checks
HEARTBEAT_TIMEOUT = 30  # seconds before disconnecting an idle client

logger = logging.getLogger(__name__)


class HeartbeatMonitor:
    """Monitor client liveness and disconnect stale connections.

    Tracks per-connection ping timestamps and runs a per-game background loop
    that disconnects connections that haven't pinged within the timeout window.
    """

    def __init__(self) -> None:
        self._last_ping: dict[str, float] = {}  # connection_id -> monotonic timestamp
        self._tasks: dict[str, asyncio.Task[None]] = {}  # game_id -> task

    def record_connect(self, connection_id: str) -> None:
        """Record initial ping timestamp for a new connection."""
        self._last_ping[connection_id] = time.monotonic()

    def record_disconnect(self, connection_id: str) -> None:
        """Remove ping tracking for a disconnected connection."""
        self._last_ping.pop(connection_id, None)

    def record_ping(self, connection_id: str) -> None:
        """Update ping timestamp for a connection."""
        self._last_ping[connection_id] = time.monotonic()

    def start_for_game(self, game_id: str, get_game: Callable[[str], Game | None]) -> None:
        """Start the heartbeat monitor for a game."""
        self._tasks[game_id] = asyncio.create_task(self._loop(game_id, get_game))

    async def stop_for_game(self, game_id: str) -> None:
        """Stop the heartbeat monitor for a game."""
        task = self._tasks.pop(game_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _loop(self, game_id: str, get_game: Callable[[str], Game | None]) -> None:
        """Periodically check for stale connections in a game."""
        while True:
            await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL)
            game = get_game(game_id)
            if game is None:
                return

            now = time.monotonic()
            for player in list(game.players.values()):
                last_ping = self._last_ping.get(player.connection_id)
                if last_ping is not None and now - last_ping > HEARTBEAT_TIMEOUT:
                    logger.info(
                        f"heartbeat timeout for {player.connection_id} in game {game_id}, disconnecting"
                    )
                    with contextlib.suppress(RuntimeError, OSError, ConnectionError):
                        await player.connection.close(code=1000, reason="heartbeat_timeout")
