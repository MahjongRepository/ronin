"""Replay collector for persisting gameplay events for post-game analysis.

Collects broadcast gameplay events and selected seat-targeted concealed events
during a game and writes them as a single-line JSON array to storage at game end. Broadcast
events capture public game state transitions (discards, melds, round end, etc.).
Seat-targeted DrawEvent carries concealed draw data (available_actions stripped).
Per-seat RoundStartedEvent views are merged into a single record with all
players' tiles for full game reconstruction. Internal prompt and error event
types are excluded.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DrawEvent,
    ErrorEvent,
    FuritenEvent,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
)
from game.messaging.event_payload import service_event_payload
from game.replay.models import REPLAY_VERSION

if TYPE_CHECKING:
    from game.logic.events import ServiceEvent
    from shared.storage import ReplayStorage

logger = logging.getLogger(__name__)

# Seat-targeted event types included in replay persistence.
# DrawEvent carries the drawn tile ID needed for full game reconstruction.
# RoundStartedEvent is handled separately via merging.
_SEAT_TARGET_INCLUDED = (DrawEvent,)

# Event types excluded from replay persistence even if broadcast-targeted.
# These are internal prompts or error signals, not gameplay state transitions.
_EXCLUDED_EVENT_TYPES = (CallPromptEvent, ErrorEvent, FuritenEvent)


class ReplayCollector:
    """Collects and persists gameplay events per game for post-game replay.

    Accepts BroadcastTarget gameplay events (discards, melds, round end, etc.)
    and selected SeatTarget events (DrawEvent for tile draws). The
    available_actions field is stripped from draw payloads. Per-seat
    RoundStartedEvent views are merged into a single record with all players'
    tiles revealed. Other SeatTarget events (prompts, errors, furiten) are
    excluded as internal signals.

    Lifecycle per game:
    1. start_game(game_id, seed) - begin tracking with the game seed
    2. collect_events(game_id, events) - accumulate qualifying events
    3. save_and_cleanup(game_id) - persist to storage and discard buffer
    4. cleanup_game(game_id) - discard buffer without persisting (abandoned game)
    """

    def __init__(self, storage: ReplayStorage) -> None:
        self._storage = storage
        self._buffers: dict[str, list[str]] = {}
        self._seeds: dict[str, str] = {}
        self._rng_versions: dict[str, str] = {}

    def start_game(self, game_id: str, seed: str, rng_version: str) -> None:
        """Begin collecting events for a game."""
        self._buffers[game_id] = []
        self._seeds[game_id] = seed
        self._rng_versions[game_id] = rng_version

    def collect_events(self, game_id: str, events: list[ServiceEvent]) -> None:
        """Append qualifying events to the game buffer.

        Per-seat RoundStartedEvent views are merged into a single record with
        all players' tiles. DrawEvent is included for draw reconstruction
        (available_actions stripped). Excluded internal types (prompts, errors,
        furiten) are skipped.
        """
        buffer = self._buffers.get(game_id)
        if buffer is None:
            return

        pending_round_started: list[ServiceEvent] = []

        for event in events:
            if isinstance(event.data, RoundStartedEvent) and isinstance(event.target, SeatTarget):
                pending_round_started.append(event)
                continue

            # Flush pending round_started events before other event types
            if pending_round_started:
                buffer.append(self._merge_round_started_payloads(pending_round_started))
                pending_round_started = []

            if not self._should_include(event):
                continue

            payload = service_event_payload(event)
            if isinstance(event.data, DrawEvent):
                payload.pop("aa", None)
            self._inject_seed_if_game_started(game_id, event, payload)
            buffer.append(json.dumps(payload, default=str))

        # Flush any remaining round_started events at end of batch
        if pending_round_started:
            buffer.append(self._merge_round_started_payloads(pending_round_started))

    @staticmethod
    def _should_include(event: ServiceEvent) -> bool:
        """Check whether a non-round-started event qualifies for replay persistence."""
        if isinstance(event.target, SeatTarget):
            return isinstance(event.data, _SEAT_TARGET_INCLUDED)
        if isinstance(event.target, BroadcastTarget):
            return not isinstance(event.data, _EXCLUDED_EVENT_TYPES)
        return False

    def _inject_seed_if_game_started(
        self,
        game_id: str,
        event: ServiceEvent,
        payload: dict[str, Any],
    ) -> None:
        """Inject the game seed into the replay payload for GameStartedEvent."""
        if isinstance(event.data, GameStartedEvent):
            seed = self._seeds.get(game_id)
            if seed is not None:
                payload["sd"] = seed
            rng_version = self._rng_versions.get(game_id)
            if rng_version is not None:
                payload["rv"] = rng_version

    @staticmethod
    def _merge_round_started_payloads(events: list[ServiceEvent]) -> str:
        """Merge per-seat RoundStartedEvent payloads into a single JSON record.

        Take the first seat's payload as the base. Extract my_tiles from each seat's
        event and store per-player tiles in the merged record for full game reconstruction.
        The my_tiles and seat fields are stripped from the merged output since each
        player's tiles are stored directly on the player dict and the per-seat
        perspective is meaningless after merging.

        Assumes the caller passes a non-empty list of RoundStartedEvent entries.
        All per-seat RoundStartedEvent entries for a round must arrive in a
        contiguous block within a single collect_events() call.
        """
        if not events:
            return "{}"
        tiles_by_seat: dict[int, list[int]] = {}
        base_payload = service_event_payload(events[0])

        for event in events:
            data: RoundStartedEvent = event.data  # type: ignore[assignment]
            tiles_by_seat[data.seat] = data.my_tiles

        for player_dict in base_payload["p"]:
            seat = player_dict["s"]
            if seat in tiles_by_seat:
                player_dict["tl"] = tiles_by_seat[seat]

        base_payload.pop("mt", None)
        base_payload.pop("s", None)

        return json.dumps(base_payload, default=str)

    async def save_and_cleanup(self, game_id: str) -> None:
        """Persist collected events to storage and discard the buffer.

        File I/O is offloaded to a worker thread to avoid blocking the
        async event loop. Errors during storage are logged but never raised,
        to avoid blocking the game-end cleanup flow.
        """
        buffer = self._buffers.pop(game_id, None)
        self._seeds.pop(game_id, None)
        self._rng_versions.pop(game_id, None)
        if buffer is None:
            return

        try:
            version_tag = json.dumps({"version": REPLAY_VERSION})
            content = "".join([version_tag, *buffer])
            await asyncio.to_thread(self._storage.save_replay, game_id, content)
        except (OSError, ValueError):  # fmt: skip
            logger.exception("Failed to save replay for game %s", game_id)

    def cleanup_game(self, game_id: str) -> None:
        """Discard the event buffer without persisting (abandoned game)."""
        self._buffers.pop(game_id, None)
        self._seeds.pop(game_id, None)
        self._rng_versions.pop(game_id, None)
