"""
Typed event classes for game events.

Events represent actions and state changes in the game that are sent to clients.
Each event has a target field indicating who should receive it:
- "all": broadcast to all players
- "seat_N": send only to player at seat N (0-3)
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel

from game.logic.enums import CallType, KanType, MeldViewType
from game.logic.types import (
    AvailableActionItem,
    GameEndResult,
    GamePlayerInfo,
    GameView,
    MeldCaller,
    RoundResult,
)


class EventType(str, Enum):
    """Types of game events sent to clients."""

    DRAW = "draw"
    DISCARD = "discard"
    MELD = "meld"
    TURN = "turn"
    CALL_PROMPT = "call_prompt"
    ROUND_END = "round_end"
    RIICHI_DECLARED = "riichi_declared"
    ERROR = "error"
    GAME_STARTED = "game_started"
    ROUND_STARTED = "round_started"
    GAME_END = "game_end"


class GameEvent(BaseModel):
    """Base class for all game events."""

    type: str
    target: str


class DrawEvent(GameEvent):
    """Event sent to a player when they draw a tile."""

    type: Literal[EventType.DRAW] = EventType.DRAW
    seat: int
    tile_id: int


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
    kan_type: KanType | None = None
    caller_seat: int
    from_seat: int | None = None  # None for closed kans
    tile_ids: list[int]


class TurnEvent(GameEvent):
    """Event sent to a player when it's their turn with available actions."""

    type: Literal[EventType.TURN] = EventType.TURN
    current_seat: int
    available_actions: list[AvailableActionItem]
    wall_count: int


class CallPromptEvent(GameEvent):
    """Event sent to players who can respond to a call opportunity."""

    type: Literal[EventType.CALL_PROMPT] = EventType.CALL_PROMPT
    call_type: CallType
    tile_id: int
    from_seat: int
    callers: list[int] | list[MeldCaller]


class RoundEndEvent(GameEvent):
    """Event broadcast when a round ends."""

    type: Literal[EventType.ROUND_END] = EventType.ROUND_END
    result: RoundResult


class RiichiDeclaredEvent(GameEvent):
    """Event broadcast when a player declares riichi."""

    type: Literal[EventType.RIICHI_DECLARED] = EventType.RIICHI_DECLARED
    seat: int


class ErrorEvent(GameEvent):
    """Event sent to a player when an error occurs."""

    type: Literal[EventType.ERROR] = EventType.ERROR
    code: str
    message: str


class GameStartedEvent(GameEvent):
    """Event broadcast to all players when the game starts."""

    type: Literal[EventType.GAME_STARTED] = EventType.GAME_STARTED
    target: str = "all"
    players: list[GamePlayerInfo]


class RoundStartedEvent(GameEvent):
    """Event sent to each player when a new round starts."""

    type: Literal[EventType.ROUND_STARTED] = EventType.ROUND_STARTED
    view: GameView


class GameEndedEvent(GameEvent):
    """Event sent when the entire game ends."""

    type: Literal[EventType.GAME_END] = EventType.GAME_END
    result: GameEndResult


Event = (
    DrawEvent
    | DiscardEvent
    | MeldEvent
    | TurnEvent
    | CallPromptEvent
    | RoundEndEvent
    | RiichiDeclaredEvent
    | ErrorEvent
    | GameStartedEvent
    | RoundStartedEvent
    | GameEndedEvent
)


class ServiceEvent(BaseModel):
    """Event transport container for game service layer."""

    event: str
    data: GameEvent
    target: str = "all"


def convert_events(raw_events: list[GameEvent]) -> list[ServiceEvent]:
    """Convert typed events to service events."""
    return [
        ServiceEvent(
            event=event.type,
            data=event,
            target=event.target,
        )
        for event in raw_events
    ]


def extract_round_result(events: list[ServiceEvent]) -> RoundResult | None:
    """Extract the round result from a list of service events."""
    for event in events:
        if event.event == EventType.ROUND_END and isinstance(event.data, RoundEndEvent):
            return event.data.result
    return None
