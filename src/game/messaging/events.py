"""
Typed event classes for game events.

Events represent actions and state changes in the game that are sent to clients.
Each event has a target field indicating who should receive it:
- "all": broadcast to all players
- "seat_N": send only to player at seat N (0-3)
"""

from typing import Literal

from pydantic import BaseModel


class GameEvent(BaseModel):
    """Base class for all game events."""

    type: str
    target: str


class DrawEvent(GameEvent):
    """Event sent to a player when they draw a tile."""

    type: Literal["draw"] = "draw"
    seat: int
    tile_id: int
    tile: str


class DiscardEvent(GameEvent):
    """Event broadcast when a player discards a tile."""

    type: Literal["discard"] = "discard"
    target: str = "all"
    seat: int
    tile_id: int
    tile: str
    is_tsumogiri: bool
    is_riichi: bool


class MeldEvent(GameEvent):
    """Event broadcast when a player calls a meld (pon, chi, kan)."""

    type: Literal["meld"] = "meld"
    target: str = "all"
    meld_type: str  # "pon", "chi", "kan"
    kan_type: str | None = None  # "open", "closed", "added" for kan
    caller_seat: int
    from_seat: int | None = None  # None for closed kans
    tile_ids: list[int]
    tiles: list[str]


class TurnEvent(GameEvent):
    """Event sent to a player when it's their turn with available actions."""

    type: Literal["turn"] = "turn"
    current_seat: int
    available_actions: list[dict]
    wall_count: int


class CallPromptEvent(GameEvent):
    """Event sent to players who can respond to a call opportunity."""

    type: Literal["call_prompt"] = "call_prompt"
    call_type: str  # "ron", "meld", "chankan"
    tile_id: int
    from_seat: int
    callers: list[int] | list[dict]  # list[int] for ron, list[dict] for meld


class RoundEndEvent(GameEvent):
    """Event broadcast when a round ends."""

    type: Literal["round_end"] = "round_end"
    result: dict


class RiichiDeclaredEvent(GameEvent):
    """Event broadcast when a player declares riichi."""

    type: Literal["riichi_declared"] = "riichi_declared"
    seat: int


class ErrorEvent(GameEvent):
    """Event sent to a player when an error occurs."""

    type: Literal["error"] = "error"
    code: str
    message: str


class PassAcknowledgedEvent(GameEvent):
    """Event sent to acknowledge a player's pass on a call opportunity."""

    type: Literal["pass_acknowledged"] = "pass_acknowledged"
    seat: int


Event = (
    DrawEvent
    | DiscardEvent
    | MeldEvent
    | TurnEvent
    | CallPromptEvent
    | RoundEndEvent
    | RiichiDeclaredEvent
    | ErrorEvent
    | PassAcknowledgedEvent
)


def event_to_wire(event: GameEvent) -> dict:
    """
    Convert a game event to wire format (dict for serialization).

    Returns a dict with all event fields that can be serialized and sent to clients.
    """
    return event.model_dump()


def convert_events(raw_events: list[GameEvent]) -> list[dict]:
    """
    Convert typed events to service events with event/data/target structure.
    """
    result = []
    for event in raw_events:
        data = event_to_wire(event)
        result.append(
            {
                "event": data["type"],
                "data": data,
                "target": data.get("target", "all"),
            }
        )
    return result


def extract_round_result(events: list[dict]) -> dict | None:
    """
    Extract the round result from a list of events.
    """
    for event in events:
        if event.get("event") == "round_end":
            return event.get("data", {}).get("result", event.get("data", {}))
    return None
