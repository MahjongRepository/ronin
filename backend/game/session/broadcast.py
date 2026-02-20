"""Shared broadcast utility for sending messages to player groups."""

import contextlib
from typing import Any


async def broadcast_to_players(
    players: dict[str, Any],
    message: dict[str, Any],
    exclude_connection_id: str | None = None,
) -> None:
    """Broadcast a message to all players, skipping one if excluded.

    Snapshot the dict values via list() to avoid RuntimeError if a
    concurrent leave mutates the dict while we yield on send_message.
    """
    for player in list(players.values()):
        if player.connection_id != exclude_connection_id:
            with contextlib.suppress(RuntimeError, OSError):
                await player.connection.send_message(message)
