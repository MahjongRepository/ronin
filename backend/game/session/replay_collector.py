from __future__ import annotations

import asyncio
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
from game.wire.keys import WireKey
from game.wire.replay_format import (
    REPLAY_VERSION,
    ReplayLineType,
    encode_replay_records,
    encode_replay_settings,
)

if TYPE_CHECKING:
    from game.logic.events import GameEvent
    from game.logic.settings import GameSettings
    from game.wire.enums import SeatControlReason
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
    One game's replay as recorded so far: the seed, RNG version and settings its game_started record carries, and the
    records.
    """

    seed: str
    rng_version: str
    settings: GameSettings
    records: list[dict[int, object]] = field(default_factory=list)


class ReplayCollector:
    """
    Shape gameplay events into replay records and persist a game's records for post-game replay.

    Accepts BroadcastTarget gameplay events (discards, melds, round end, etc.)
    and selected SeatTarget events (DrawEvent for tile draws). The
    available_actions field is stripped from draw payloads. Per-seat
    RoundStartedEvent views are merged into a single record with all players'
    tiles revealed. Other SeatTarget events (prompts, errors, furiten) are
    excluded as internal signals.

    It also writes the replay-only seat control records the session reports: an AI replacement ahead of the AI player's
    moves, and a human return.

    The collector keeps no per-game state: each game holds its own ReplayRecord (on its GameSession) from the start
    until its end detaches the records, which `save` then persists.
    """

    def __init__(self, storage: ReplayStorage) -> None:
        self._storage = storage

    def collect_events(self, record: ReplayRecord, events: list[GameEvent]) -> None:
        """
        Append the qualifying events to the record's records.

        Per-seat RoundStartedEvent views are merged into a single record with all players' tiles. DrawEvent is included
        for draw reconstruction (available_actions stripped). Excluded internal types (prompts, errors, furiten) are
        skipped.
        """
        buffer = record.records
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
                payload.pop(WireKey.AVAILABLE_ACTIONS, None)

            if isinstance(event, GameStartedEvent):
                payload[WireKey.HAS_AKADORA] = record.settings.has_akadora
                payload[WireKey.SEED] = record.seed
                payload[WireKey.RNG_VERSION] = record.rng_version
                payload[WireKey.GAME_SETTINGS] = encode_replay_settings(record.settings)

            buffer.append(payload)

        # Flush any remaining round_started events at end of batch
        if pending_round_started:
            buffer.append(self._merge_round_started_payloads(pending_round_started))

    @staticmethod
    def record_ai_replacement(record: ReplayRecord, *, seat: int, reason: SeatControlReason) -> None:
        """
        Append the seat control record of a seat's replacement with an AI player, to precede the events of its moves.
        """
        record.records.append(
            {
                WireKey.EVENT_TYPE: ReplayLineType.SEAT_CONTROL,
                WireKey.SEAT: seat,
                WireKey.AI_PLAYER: 1,
                WireKey.SEAT_CONTROL_REASON: reason,
            }
        )

    @staticmethod
    def record_human_return(record: ReplayRecord, *, seat: int) -> None:
        """
        Append the seat control record of a seat's human return: its participant takes it back from the AI player.
        """
        record.records.append(
            {WireKey.EVENT_TYPE: ReplayLineType.SEAT_CONTROL, WireKey.SEAT: seat, WireKey.AI_PLAYER: 0}
        )

    @staticmethod
    def _should_include(event: GameEvent) -> bool:
        """
        Check whether a non-round-started event qualifies for replay persistence.
        """
        if isinstance(event.target, SeatTarget):
            return isinstance(event, _SEAT_TARGET_INCLUDED)

        return not isinstance(event, _EXCLUDED_EVENT_TYPES)

    @staticmethod
    def _merge_round_started_payloads(events: list[RoundStartedEvent]) -> dict[int, object]:
        """
        Merge per-seat RoundStartedEvent payloads into a single record.

        Take the first seat's payload as the base. Extract my_tiles from each seat's event and store per-player tiles in
        the merged record for full game reconstruction. The my_tiles and seat fields are stripped from the merged output
        since each player's tiles are stored directly on the player dict and the per-seat perspective is meaningless
        after merging.

        Assumes the caller passes a non-empty list of RoundStartedEvent entries. All per-seat RoundStartedEvent entries
        for a round must arrive in a contiguous block within a single collect_events() call.
        """
        if not events:
            return {}

        tiles_by_seat: dict[int, list[int]] = {}
        for event in events:
            tiles_by_seat[event.seat] = event.my_tiles

        base_payload = game_event_payload(events[0])
        for player_dict in base_payload[WireKey.PLAYERS]:
            seat = player_dict[WireKey.SEAT]
            if seat in tiles_by_seat:
                player_dict[WireKey.TILES] = tiles_by_seat[seat]

        base_payload.pop(WireKey.MY_TILES, None)
        base_payload.pop(WireKey.SEAT, None)

        return base_payload

    async def save(self, game_id: str, records: list[dict[int, object]]) -> None:
        """
        Persist a game's detached replay records.

        Encoding and file I/O run together in a worker thread to avoid blocking the async event loop. An encoding or
        storage error propagates to the caller, whose game-end finalizer turns the end into a failure.
        """
        await asyncio.to_thread(encode_and_store_replay, self._storage, game_id, records)


def encode_and_store_replay(storage: ReplayStorage, game_id: str, records: list[dict[int, object]]) -> None:
    """
    Encode a game's replay records behind the version header and save them to storage.
    """
    content = encode_replay_records([{WireKey.REPLAY_VERSION: REPLAY_VERSION}, *records])
    storage.save_replay(game_id, content)
