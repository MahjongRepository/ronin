"""Domain event models and service event transport container.

Domain event classes are the canonical event types for the game logic layer.
ServiceEvent is the transport wrapper used to route events to clients.
convert_events() maps domain events into ServiceEvent containers with typed
routing targets.

All layers import exclusively from this module for event types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from game.logic.enums import CallType, GameErrorCode, MeldViewType
from game.logic.types import (
    AvailableActionItem,
    GameEndResult,
    GamePlayerInfo,
    GameView,
    MeldCaller,
    RoundResult,
)

# ---------------------------------------------------------------------------
# Typed routing targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BroadcastTarget:
    """Event should be sent to all players in the game."""


@dataclass(frozen=True)
class SeatTarget:
    """Event should be sent to a specific seat."""

    seat: int


EventTarget = BroadcastTarget | SeatTarget


def parse_wire_target(value: str) -> EventTarget:
    """Parse a legacy string target into a typed EventTarget."""
    if value == "all":
        return BroadcastTarget()
    if value.startswith("seat_"):
        return SeatTarget(seat=int(value.split("_")[1]))
    raise ValueError(f"invalid target value: {value}")


# ---------------------------------------------------------------------------
# Event type enum
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    """Types of game events."""

    DRAW = "draw"
    DISCARD = "discard"
    MELD = "meld"
    CALL_PROMPT = "call_prompt"
    ROUND_END = "round_end"
    RIICHI_DECLARED = "riichi_declared"
    DORA_REVEALED = "dora_revealed"
    ERROR = "error"
    GAME_STARTED = "game_started"
    ROUND_STARTED = "round_started"
    GAME_END = "game_end"
    FURITEN = "furiten"


# ---------------------------------------------------------------------------
# Domain event models
# ---------------------------------------------------------------------------


class GameEvent(BaseModel):
    """Base class for all domain game events."""

    model_config = ConfigDict(frozen=True)

    type: EventType
    target: str


class DrawEvent(GameEvent):
    """Event sent to a player when they draw a tile (or get their turn after a meld)."""

    type: Literal[EventType.DRAW] = EventType.DRAW
    seat: int
    tile_id: int | None = None
    available_actions: list[AvailableActionItem] = Field(default_factory=list)


class DiscardEvent(GameEvent):
    """Event broadcast when a player discards a tile."""

    type: Literal[EventType.DISCARD] = EventType.DISCARD
    target: str = "all"
    seat: int
    tile_id: int
    is_tsumogiri: bool
    is_riichi: bool


class MeldEvent(GameEvent):
    """Event broadcast when a player calls a meld (pon, chi, kan)."""

    type: Literal[EventType.MELD] = EventType.MELD
    target: str = "all"
    meld_type: MeldViewType
    caller_seat: int
    from_seat: int | None = None
    tile_ids: list[int]
    called_tile_id: int | None = None


class CallPromptEvent(GameEvent):
    """Event sent to players who can respond to a call opportunity."""

    type: Literal[EventType.CALL_PROMPT] = EventType.CALL_PROMPT
    call_type: CallType
    tile_id: int
    from_seat: int
    callers: list[int | MeldCaller]


class RoundEndEvent(GameEvent):
    """Event broadcast when a round ends."""

    type: Literal[EventType.ROUND_END] = EventType.ROUND_END
    result: RoundResult


class RiichiDeclaredEvent(GameEvent):
    """Event broadcast when a player declares riichi."""

    type: Literal[EventType.RIICHI_DECLARED] = EventType.RIICHI_DECLARED
    seat: int


class DoraRevealedEvent(GameEvent):
    """Event broadcast when a new dora indicator is revealed (after kan)."""

    type: Literal[EventType.DORA_REVEALED] = EventType.DORA_REVEALED
    target: str = "all"
    tile_id: int


class ErrorEvent(GameEvent):
    """Event sent to a player when an error occurs."""

    type: Literal[EventType.ERROR] = EventType.ERROR
    code: GameErrorCode
    message: str


class GameStartedEvent(GameEvent):
    """Event broadcast to all players when the game starts."""

    type: Literal[EventType.GAME_STARTED] = EventType.GAME_STARTED
    target: str = "all"
    game_id: str
    players: list[GamePlayerInfo]


class RoundStartedEvent(GameEvent):
    """Event sent to each player when a new round starts."""

    type: Literal[EventType.ROUND_STARTED] = EventType.ROUND_STARTED
    view: GameView


class GameEndedEvent(GameEvent):
    """Event sent when the entire game ends."""

    type: Literal[EventType.GAME_END] = EventType.GAME_END
    result: GameEndResult


class FuritenEvent(GameEvent):
    """Event sent to a player when their furiten state changes."""

    type: Literal[EventType.FURITEN] = EventType.FURITEN
    is_furiten: bool


Event = (
    DrawEvent
    | DiscardEvent
    | MeldEvent
    | CallPromptEvent
    | RoundEndEvent
    | RiichiDeclaredEvent
    | DoraRevealedEvent
    | ErrorEvent
    | GameStartedEvent
    | RoundStartedEvent
    | GameEndedEvent
    | FuritenEvent
)


# ---------------------------------------------------------------------------
# Service event transport container
# ---------------------------------------------------------------------------


def _normalize_event_value(value: str | Enum) -> str:
    if isinstance(value, Enum):
        return value.value
    return value


class ServiceEvent(BaseModel):
    """Event transport container for game service layer.

    Uses typed internal targets (BroadcastTarget / SeatTarget) for routing.
    """

    model_config = {"arbitrary_types_allowed": True}

    event: EventType
    data: GameEvent
    target: EventTarget = BroadcastTarget()

    @model_validator(mode="after")
    def _ensure_event_matches_data(self) -> ServiceEvent:
        event_value = _normalize_event_value(self.event)
        data_value = _normalize_event_value(self.data.type)
        if event_value != data_value:
            raise ValueError(f"ServiceEvent.event '{event_value}' does not match data.type '{data_value}'")
        return self


# ---------------------------------------------------------------------------
# Event conversion helpers
# ---------------------------------------------------------------------------


def _get_unique_caller_seats(callers: list[int | MeldCaller]) -> list[int]:
    """Extract unique seat numbers from callers list."""
    seen: set[int] = set()
    seats: list[int] = []
    for caller in callers:
        seat = caller if isinstance(caller, int) else caller.seat
        if seat not in seen:
            seen.add(seat)
            seats.append(seat)
    return seats


def _filter_callers_for_seat(callers: list[int | MeldCaller], seat: int) -> list[int | MeldCaller]:
    """Filter callers list to only include entries for the given seat."""
    if callers and isinstance(callers[0], int):
        return [c for c in callers if isinstance(c, int) and c == seat]
    return [c for c in callers if isinstance(c, MeldCaller) and c.seat == seat]


def _split_discard_prompt_for_seat(event: CallPromptEvent, seat: int) -> CallPromptEvent:
    """Split a DISCARD prompt into one per-seat event.

    Ron-dominant: if seat has both ron and meld entries, produce a RON prompt.
    """
    is_ron = any(c == seat for c in event.callers if isinstance(c, int))
    meld_callers: list[int | MeldCaller] = [
        c for c in event.callers if isinstance(c, MeldCaller) and c.seat == seat
    ]

    if is_ron:
        return event.model_copy(
            update={
                "call_type": CallType.RON,
                "callers": [seat],
            }
        )
    return event.model_copy(
        update={
            "call_type": CallType.MELD,
            "callers": meld_callers,
        }
    )


def convert_events(raw_events: list[GameEvent]) -> list[ServiceEvent]:
    """Convert typed events to service events with typed targets.

    CallPromptEvent is split into per-caller-seat events with callers filtered
    to only the recipient's entries. Each ServiceEvent carries a distinct
    CallPromptEvent instance (no shared mutable data).

    DISCARD prompts are split per-seat with the appropriate call_type
    for each seat (RON for ron callers, MELD for meld callers).
    """
    result: list[ServiceEvent] = []
    for event in raw_events:
        if isinstance(event, CallPromptEvent):
            if event.call_type == CallType.DISCARD:
                for seat in _get_unique_caller_seats(event.callers):
                    per_seat_event = _split_discard_prompt_for_seat(event, seat)
                    result.append(
                        ServiceEvent(event=event.type, data=per_seat_event, target=SeatTarget(seat=seat))
                    )
            else:
                for seat in _get_unique_caller_seats(event.callers):
                    per_seat_callers = _filter_callers_for_seat(event.callers, seat)
                    per_seat_event = event.model_copy(update={"callers": per_seat_callers})
                    result.append(
                        ServiceEvent(event=event.type, data=per_seat_event, target=SeatTarget(seat=seat))
                    )
        else:
            result.append(
                ServiceEvent(
                    event=event.type,
                    data=event,
                    target=parse_wire_target(event.target),
                )
            )
    return result


def extract_round_result(events: list[ServiceEvent]) -> RoundResult | None:
    """Extract the round result from a list of service events."""
    for event in events:
        if event.event == EventType.ROUND_END and isinstance(event.data, RoundEndEvent):
            return event.data.result
    return None
