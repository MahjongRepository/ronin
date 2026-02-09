"""Replay collector for persisting gameplay events for post-game analysis.

Collects broadcast gameplay events and selected seat-targeted concealed events
during a game and writes them as JSON lines to storage at game end. Broadcast
events capture public game state transitions (discards, melds, round end, etc.).
Seat-targeted DrawEvent and RoundStartedEvent carry concealed data (draw tiles,
per-seat initial hands) needed for full game reconstruction. Internal prompt and
error event types are excluded.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DrawEvent,
    ErrorEvent,
    FuritenEvent,
    RoundStartedEvent,
    SeatTarget,
    TurnEvent,
)
from game.messaging.event_payload import service_event_payload, service_event_target

if TYPE_CHECKING:
    from game.logic.events import ServiceEvent
    from shared.storage import ReplayStorage

logger = logging.getLogger(__name__)

# Seat-targeted event types included in replay persistence.
# DrawEvent carries the drawn tile ID; RoundStartedEvent carries per-seat
# concealed hand data. Both are needed for full game reconstruction.
_SEAT_TARGET_INCLUDED = (DrawEvent, RoundStartedEvent)

# Event types excluded from replay persistence even if broadcast-targeted.
# These are internal prompts or error signals, not gameplay state transitions.
_EXCLUDED_EVENT_TYPES = (TurnEvent, CallPromptEvent, ErrorEvent, FuritenEvent)


class ReplayCollector:
    """Collects and persists gameplay events per game for post-game replay.

    Accepts BroadcastTarget gameplay events (discards, melds, round end, etc.)
    and selected SeatTarget events (DrawEvent for tile draws, RoundStartedEvent
    for per-seat concealed hand data). Other SeatTarget events (turns, prompts,
    errors, furiten) are excluded as they are internal signals.

    Lifecycle per game:
    1. start_game(game_id) - begin tracking
    2. collect_events(game_id, events) - accumulate qualifying events
    3. save_and_cleanup(game_id) - persist to storage and discard buffer
    4. cleanup_game(game_id) - discard buffer without persisting (abandoned game)
    """

    def __init__(self, storage: ReplayStorage) -> None:
        self._storage = storage
        self._buffers: dict[str, list[str]] = {}

    def start_game(self, game_id: str) -> None:
        """Begin collecting events for a game."""
        self._buffers[game_id] = []

    def collect_events(self, game_id: str, events: list[ServiceEvent]) -> None:
        """Append qualifying events to the game buffer.

        For SeatTarget events, only DrawEvent and RoundStartedEvent are included
        (concealed data for replay). All other SeatTarget events are skipped.
        For BroadcastTarget events, excluded internal types (turns, prompts,
        errors, furiten) are skipped.
        """
        buffer = self._buffers.get(game_id)
        if buffer is None:
            return

        for event in events:
            if isinstance(event.target, SeatTarget):
                if not isinstance(event.data, _SEAT_TARGET_INCLUDED):
                    continue
            elif isinstance(event.target, BroadcastTarget):
                if isinstance(event.data, _EXCLUDED_EVENT_TYPES):
                    continue
            else:
                continue

            payload = service_event_payload(event)
            target_str = service_event_target(event)
            record = {"target": target_str, **payload}
            buffer.append(json.dumps(record, default=str))

    async def save_and_cleanup(self, game_id: str) -> None:
        """Persist collected events to storage and discard the buffer.

        File I/O is offloaded to a worker thread to avoid blocking the
        async event loop. Errors during storage are logged but never raised,
        to avoid blocking the game-end cleanup flow.
        """
        buffer = self._buffers.pop(game_id, None)
        if buffer is None:
            return

        try:
            content = "\n".join(buffer)
            await asyncio.to_thread(self._storage.save_replay, game_id, content)
        except (OSError, ValueError):
            logger.exception("Failed to save replay for game %s", game_id)

    def cleanup_game(self, game_id: str) -> None:
        """Discard the event buffer without persisting (abandoned game)."""
        self._buffers.pop(game_id, None)
