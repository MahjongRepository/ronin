"""Monitor client liveness via application-level heartbeat."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

HEARTBEAT_CHECK_INTERVAL = 5  # seconds between heartbeat checks
HEARTBEAT_TIMEOUT = 30  # seconds before disconnecting an idle client

logger = logging.getLogger(__name__)


class _HasPlayers(Protocol):
    """Entity with a players dict (Game or Room)."""

    @property
    def players(self) -> dict[str, Any]: ...


# Callback that resolves an entity (game or room) by ID.
# Returns an object with a `.players` dict or None if the entity is gone.
EntityResolver = Callable[[str], _HasPlayers | None]


class HeartbeatMonitor:
    """Monitor client liveness and disconnect stale connections.

    Tracks per-connection ping timestamps and runs per-game and per-room
    background loops that disconnect connections that haven't pinged within
    the timeout window.
    """

    def __init__(self) -> None:
        self._last_ping: dict[str, float] = {}  # connection_id -> monotonic timestamp
        self._tasks: dict[str, asyncio.Task[None]] = {}  # "game:{id}" or "room:{id}" -> task

    def record_connect(self, connection_id: str) -> None:
        """Record initial ping timestamp for a new connection."""
        self._last_ping[connection_id] = time.monotonic()

    def record_disconnect(self, connection_id: str) -> None:
        """Remove ping tracking for a disconnected connection."""
        self._last_ping.pop(connection_id, None)

    def record_ping(self, connection_id: str) -> None:
        """Update ping timestamp for a tracked connection."""
        if connection_id in self._last_ping:
            self._last_ping[connection_id] = time.monotonic()

    def start_for_game(self, game_id: str, get_game: EntityResolver) -> None:
        """Start the heartbeat monitor for a game."""
        self._start(f"game:{game_id}", game_id, "game", get_game)

    def start_for_room(self, room_id: str, get_room: EntityResolver) -> None:
        """Start the heartbeat monitor for a room."""
        self._start(f"room:{room_id}", room_id, "room", get_room)

    async def stop_for_game(self, game_id: str) -> None:
        """Stop the heartbeat monitor for a game."""
        await self._stop(f"game:{game_id}")

    async def stop_for_room(self, room_id: str) -> None:
        """Stop the heartbeat monitor for a room."""
        await self._stop(f"room:{room_id}")

    def _start(self, key: str, entity_id: str, entity_type: str, get_entity: EntityResolver) -> None:
        existing = self._tasks.get(key)
        if existing is not None and not existing.done():
            existing.cancel()
        self._tasks[key] = asyncio.create_task(self._check_loop(entity_id, entity_type, get_entity))

    async def _stop(self, key: str) -> None:
        task = self._tasks.pop(key, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _check_loop(self, entity_id: str, entity_type: str, get_entity: EntityResolver) -> None:
        """Periodically check for stale connections in a game or room."""
        while True:
            await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL)
            entity = get_entity(entity_id)
            if entity is None:
                return

            now = time.monotonic()
            for player in list(entity.players.values()):
                last_ping = self._last_ping.get(player.connection_id)
                if last_ping is not None and now - last_ping > HEARTBEAT_TIMEOUT:
                    logger.info(
                        "heartbeat timeout for %s in %s %s, disconnecting",
                        player.connection_id,
                        entity_type,
                        entity_id,
                    )
                    with contextlib.suppress(RuntimeError, OSError, ConnectionError):
                        await player.connection.close(code=1000, reason="heartbeat_timeout")
