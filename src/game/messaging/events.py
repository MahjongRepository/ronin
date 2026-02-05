"""
Typed event classes for game events.

Events represent actions and state changes in the game that are sent to clients.
Each event has a target field indicating who should receive it:
- "all": broadcast to all players
- "seat_N": send only to player at seat N (0-3)
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, model_validator

from game.logic.enums import CallType, GameErrorCode, KanType, MeldViewType
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
    DORA_REVEALED = "dora_revealed"
    ERROR = "error"
    GAME_STARTED = "game_started"
    ROUND_STARTED = "round_started"
    GAME_END = "game_end"
    FURITEN = "furiten"


def _normalize_event_value(value: str | Enum) -> str:
    if isinstance(value, Enum):
        return value.value
    return value


class GameEvent(BaseModel):
    """Base class for all game events."""

    type: EventType
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
    called_tile_id: int | None = None  # tile taken from discard, None for closed/added kans


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


class DoraRevealedEvent(GameEvent):
    """Event broadcast when a new dora indicator is revealed (after kan)."""

    type: Literal[EventType.DORA_REVEALED] = EventType.DORA_REVEALED
    target: str = "all"
    tile_id: int  # the new dora indicator tile
    dora_indicators: list[int]  # full list of current dora indicators (for state sync)


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
    | TurnEvent
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


class ServiceEvent(BaseModel):
    """Event transport container for game service layer."""

    event: EventType
    data: GameEvent
    target: str = "all"

    @model_validator(mode="after")
    def _ensure_event_matches_data(self) -> ServiceEvent:
        event_value = _normalize_event_value(self.event)
        data_value = _normalize_event_value(self.data.type)
        if event_value != data_value:
            raise ValueError(f"ServiceEvent.event '{event_value}' does not match data.type '{data_value}'")
        return self


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
