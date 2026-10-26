from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from game.logic.events import (
    CallPromptEvent,
    DrawEvent,
    ErrorEvent,
    FuritenEvent,
    GameStartedEvent,
    RoundStartedEvent,
    SeatTarget,
)
from game.messaging.event_payload import game_event_payload
from game.wire.replay_format import REPLAY_VERSION, encode_replay_settings

if TYPE_CHECKING:
    from game.logic.events import GameEvent
    from game.logic.settings import GameSettings
    from shared.storage import ReplayStorage

# Seat-targeted event types included in replay persistence.
# DrawEvent carries the drawn tile ID needed for full game reconstruction.
# RoundStartedEvent is handled separately via merging.
_SEAT_TARGET_INCLUDED = (DrawEvent,)

# Event types excluded from replay persistence even if broadcast-targeted.
# These are internal prompts or error signals, not gameplay state transitions.
_EXCLUDED_EVENT_TYPES = (CallPromptEvent, ErrorEvent, FuritenEvent)


@dataclass
class ReplayRecord:
    """
    One game's replay as recorded so far: the seed, RNG version and settings its game_started line carries, and the
    lines.
    """

    seed: str
    rng_version: str
    settings: GameSettings
    lines: list[str] = field(default_factory=list)


class ReplayCollector:
    """
    Shape gameplay events into replay lines and persist a game's lines for post-game replay.

    Accepts BroadcastTarget gameplay events (discards, melds, round end, etc.)
    and selected SeatTarget events (DrawEvent for tile draws). The
    available_actions field is stripped from draw payloads. Per-seat
    RoundStartedEvent views are merged into a single record with all players'
    tiles revealed. Other SeatTarget events (prompts, errors, furiten) are
    excluded as internal signals.

    The collector keeps no per-game state: each game holds its own ReplayRecord (on its GameSession) from the start
    until its end detaches the lines, which `save` then persists.
    """

    def __init__(self, storage: ReplayStorage) -> None:
        self._storage = storage

    def collect_events(self, record: ReplayRecord, events: list[GameEvent]) -> None:
        """
        Append the qualifying events to the record's lines.

        Per-seat RoundStartedEvent views are merged into a single record with all players' tiles. DrawEvent is included
        for draw reconstruction (available_actions stripped). Excluded internal types (prompts, errors, furiten) are
        skipped.
        """
        buffer = record.lines
        pending_round_started: list[RoundStartedEvent] = []
        for event in events:
            if isinstance(event, RoundStartedEvent) and isinstance(event.target, SeatTarget):
                pending_round_started.append(event)
                continue

            # Flush pending round_started events before other event types
            if pending_round_started:
                buffer.append(self._merge_round_started_payloads(pending_round_started))
                pending_round_started = []

            if not self._should_include(event):
                continue

            payload = game_event_payload(event)
            if isinstance(event, DrawEvent):
                payload.pop("aa", None)

            if isinstance(event, GameStartedEvent):
                payload["sd"] = record.seed
                payload["rv"] = record.rng_version
                payload["gs"] = encode_replay_settings(record.settings)

            buffer.append(json.dumps(payload, default=str))

        # Flush any remaining round_started events at end of batch
        if pending_round_started:
            buffer.append(self._merge_round_started_payloads(pending_round_started))

    @staticmethod
    def _should_include(event: GameEvent) -> bool:
        """
        Check whether a non-round-started event qualifies for replay persistence.
        """
        if isinstance(event.target, SeatTarget):
            return isinstance(event, _SEAT_TARGET_INCLUDED)

        return not isinstance(event, _EXCLUDED_EVENT_TYPES)

    @staticmethod
    def _merge_round_started_payloads(events: list[RoundStartedEvent]) -> str:
        """
        Merge per-seat RoundStartedEvent payloads into a single JSON record.

        Take the first seat's payload as the base. Extract my_tiles from each seat's event and store per-player tiles in
        the merged record for full game reconstruction. The my_tiles and seat fields are stripped from the merged output
        since each player's tiles are stored directly on the player dict and the per-seat perspective is meaningless
        after merging.

        Assumes the caller passes a non-empty list of RoundStartedEvent entries. All per-seat RoundStartedEvent entries
        for a round must arrive in a contiguous block within a single collect_events() call.
        """
        if not events:
            return "{}"

        tiles_by_seat: dict[int, list[int]] = {}
        for event in events:
            tiles_by_seat[event.seat] = event.my_tiles

        base_payload = game_event_payload(events[0])
        for player_dict in base_payload["p"]:
            seat = player_dict["s"]
            if seat in tiles_by_seat:
                player_dict["tl"] = tiles_by_seat[seat]

        base_payload.pop("mt", None)
        base_payload.pop("s", None)

        return json.dumps(base_payload, default=str)

    async def save(self, game_id: str, lines: list[str]) -> None:
        """
        Persist a game's detached replay lines.

        File I/O is offloaded to a worker thread to avoid blocking the async event loop. A storage error propagates to
        the caller, whose game-end finalizer turns the end into a failure.
        """
        version_tag = json.dumps({"version": REPLAY_VERSION})
        content = "\n".join([version_tag, *lines])
        await asyncio.to_thread(self._storage.save_replay, game_id, content)
