from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from game.logic.enums import CallType, GameErrorCode, MeldViewType, PromptKind
from game.logic.types import (
    AvailableActionItem,
    GamePlayerInfo,
    MeldCaller,
    PlayerStanding,
    PlayerView,
    RoundResult,
    WireCallTypeField,
    WireWindField,
)

if TYPE_CHECKING:
    from game.logic.state import PendingCallPrompt

# ---------------------------------------------------------------------------
# Typed routing targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BroadcastTarget:
    """
    Event should be sent to all players in the game.
    """


@dataclass(frozen=True)
class SeatTarget:
    """
    Event should be sent to a specific seat.
    """

    seat: int


EventTarget = BroadcastTarget | SeatTarget

# Reusable singleton — BroadcastTarget is frozen and stateless.
_BROADCAST = BroadcastTarget()


# ---------------------------------------------------------------------------
# Event type enum
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    """
    Types of game events.
    """

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
    """
    Base class for all domain game events, each addressed to everyone or to one seat.
    """

    model_config = ConfigDict(frozen=True)

    type: EventType
    target: EventTarget


class DrawEvent(GameEvent):
    """
    Event sent to a player when they draw a tile.
    """

    type: Literal[EventType.DRAW] = EventType.DRAW
    seat: int
    tile_id: int
    available_actions: list[AvailableActionItem] = Field(default_factory=list)


class DiscardEvent(GameEvent):
    """
    Event broadcast when a player discards a tile.
    """

    type: Literal[EventType.DISCARD] = EventType.DISCARD
    target: EventTarget = _BROADCAST
    seat: int
    tile_id: int
    is_tsumogiri: bool = False
    is_riichi: bool = False


class MeldEvent(GameEvent):
    """
    Event broadcast when a player calls a meld (pon, chi, kan).
    """

    type: Literal[EventType.MELD] = EventType.MELD
    target: EventTarget = _BROADCAST
    meld_type: MeldViewType
    caller_seat: int
    from_seat: int | None = None
    tile_ids: list[int]
    called_tile_id: int | None = None


class CallPromptEvent(GameEvent):
    """
    Event sent to players who can respond to a call opportunity.
    """

    type: Literal[EventType.CALL_PROMPT] = EventType.CALL_PROMPT
    call_type: WireCallTypeField = Field(serialization_alias="clt")
    tile_id: int = Field(serialization_alias="ti")
    from_seat: int = Field(serialization_alias="frs")
    callers: list[int | MeldCaller] = Field(serialization_alias="clr")


class RoundEndEvent(GameEvent):
    """
    Event broadcast when a round ends.
    """

    type: Literal[EventType.ROUND_END] = EventType.ROUND_END
    target: EventTarget = _BROADCAST
    result: RoundResult


class RiichiDeclaredEvent(GameEvent):
    """
    Event broadcast when a player declares riichi.
    """

    type: Literal[EventType.RIICHI_DECLARED] = EventType.RIICHI_DECLARED
    target: EventTarget = _BROADCAST
    seat: int = Field(serialization_alias="s")


class DoraRevealedEvent(GameEvent):
    """
    Event broadcast when a new dora indicator is revealed (after kan).
    """

    type: Literal[EventType.DORA_REVEALED] = EventType.DORA_REVEALED
    target: EventTarget = _BROADCAST
    tile_id: int = Field(serialization_alias="ti")


class ErrorEvent(GameEvent):
    """
    Event sent to a player when an error occurs.
    """

    type: Literal[EventType.ERROR] = EventType.ERROR
    code: GameErrorCode = Field(serialization_alias="cd")
    message: str = Field(serialization_alias="msg")


class GameStartedEvent(GameEvent):
    """
    Event broadcast to all players when the game starts.
    """

    type: Literal[EventType.GAME_STARTED] = EventType.GAME_STARTED
    target: EventTarget = _BROADCAST
    game_id: str = Field(serialization_alias="gid")
    players: list[GamePlayerInfo] = Field(serialization_alias="p")
    dealer_seat: int = Field(serialization_alias="dl")
    dealer_dice: tuple[tuple[int, int], tuple[int, int]] = Field(serialization_alias="dd")


class RoundStartedEvent(GameEvent):
    """
    Event sent to each player when a new round starts.
    """

    type: Literal[EventType.ROUND_STARTED] = EventType.ROUND_STARTED
    seat: int = Field(serialization_alias="s")
    round_wind: WireWindField = Field(serialization_alias="w")
    round_number: int = Field(serialization_alias="n")
    dealer_seat: int = Field(serialization_alias="dl")
    current_player_seat: int = Field(serialization_alias="cp")
    dora_indicators: list[int] = Field(serialization_alias="di")
    honba_sticks: int = Field(serialization_alias="h")
    riichi_sticks: int = Field(serialization_alias="r")
    my_tiles: list[int] = Field(serialization_alias="mt")
    players: list[PlayerView] = Field(serialization_alias="p")
    dice: tuple[int, int] = Field(default=(1, 1), serialization_alias="dc")


class GameEndedEvent(GameEvent):
    """
    Event sent when the entire game ends.
    """

    type: Literal[EventType.GAME_END] = EventType.GAME_END
    target: EventTarget = _BROADCAST
    winner_seat: int = Field(serialization_alias="ws")
    standings: list[PlayerStanding] = Field(serialization_alias="st")
    num_rounds: int = Field(default=0, serialization_alias="nr")


class FuritenEvent(GameEvent):
    """
    Event sent to a player when their furiten state changes.
    """

    type: Literal[EventType.FURITEN] = EventType.FURITEN
    is_furiten: bool = Field(serialization_alias="f")


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


class ServiceEvent(BaseModel):
    """
    Event transport container for game service layer: the domain event, with its type and routing target read from it.
    """

    data: GameEvent

    @property
    def event(self) -> EventType:
        """
        The type of the wrapped event.
        """
        return self.data.type

    @property
    def target(self) -> EventTarget:
        """
        Where the wrapped event goes: every player or one seat.
        """
        return self.data.target


# ---------------------------------------------------------------------------
# Event conversion helpers
# ---------------------------------------------------------------------------


def build_call_prompt_events(prompt: PendingCallPrompt) -> list[CallPromptEvent]:
    """
    Build the prompt's per-seat call prompt events: one per caller, in prompt order, each addressed to its seat.

    On a discard prompt a ron caller gets a RON event and a meld caller a MELD event listing its melds; on a chankan
    prompt every caller gets a CHANKAN event.
    """
    events: list[CallPromptEvent] = []
    for caller in prompt.callers:
        callers: list[int | MeldCaller] = [caller.seat]
        if prompt.kind == PromptKind.CHANKAN:
            call_type = CallType.CHANKAN
        elif caller.can_ron:
            call_type = CallType.RON
        else:
            call_type = CallType.MELD
            callers = [MeldCaller(seat=caller.seat, call_type=m.call_type, options=m.options) for m in caller.melds]

        events.append(
            CallPromptEvent(
                call_type=call_type,
                tile_id=prompt.tile_id,
                from_seat=prompt.from_seat,
                callers=callers,
                target=SeatTarget(seat=caller.seat),
            ),
        )

    return events


def convert_events(raw_events: list[GameEvent]) -> list[ServiceEvent]:
    """
    Wrap domain events in service events.

    Builds each ServiceEvent with model_construct, skipping validation of an event that is already a validated model, as
    this runs for every event.
    """
    _construct = ServiceEvent.model_construct
    return [_construct(data=event) for event in raw_events]
