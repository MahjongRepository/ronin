"""Transport event compatibility facade.

All event types, transport containers, and conversion utilities are defined
in game.logic.events. This module re-exports them for backward compatibility
so that existing consumers (replay, tests, session layer) can continue
importing from game.messaging.events during the migration window.
"""

from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DiscardEvent,
    DoraRevealedEvent,
    DrawEvent,
    ErrorEvent,
    Event,
    EventTarget,
    EventType,
    FuritenEvent,
    GameEndedEvent,
    GameEvent,
    GameStartedEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    RoundStartedEvent,
    SeatTarget,
    ServiceEvent,
    TurnEvent,
    convert_events,
    extract_round_result,
    parse_wire_target,
)

__all__ = [
    "BroadcastTarget",
    "CallPromptEvent",
    "DiscardEvent",
    "DoraRevealedEvent",
    "DrawEvent",
    "ErrorEvent",
    "Event",
    "EventTarget",
    "EventType",
    "FuritenEvent",
    "GameEndedEvent",
    "GameEvent",
    "GameStartedEvent",
    "MeldEvent",
    "RiichiDeclaredEvent",
    "RoundEndEvent",
    "RoundStartedEvent",
    "SeatTarget",
    "ServiceEvent",
    "TurnEvent",
    "convert_events",
    "extract_round_result",
    "parse_wire_target",
]
