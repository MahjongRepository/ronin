from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from game.logic.enums import GameEndCause, MeldViewType, WindName
from game.logic.settings import GameType
from game.logic.types import (
    PlayerStanding,
    PlayerView,
    RoundResult,
)

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
    DRAW_NOTICE = "draw_notice"
    DISCARD = "discard"
    MELD = "meld"
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
    Event sent to the player who draws a tile, with the live wall's tiles left after it.

    Every other seat gets a DrawNoticeEvent of the same draw instead.
    """

    type: Literal[EventType.DRAW] = EventType.DRAW
    seat: int
    tile_id: int
    tiles_remaining: int


class DrawNoticeEvent(GameEvent):
    """
    Event sent to each seat but the drawer's when a player draws a tile: the drawer's seat, never the tile.
    """

    type: Literal[EventType.DRAW_NOTICE] = EventType.DRAW_NOTICE
    seat: int


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
    added_tile_id: int | None = None


class RoundEndEvent(GameEvent):
    """
    Event broadcast when a round ends, with the riichi sticks its result leaves on the table and the round's dealer and
    revealed dora indicators, so a client shows the result from the server's word rather than its own table.
    """

    type: Literal[EventType.ROUND_END] = EventType.ROUND_END
    target: EventTarget = _BROADCAST
    result: RoundResult
    riichi_sticks: int
    dealer_seat: int
    dora_indicators: list[int]


class RiichiDeclaredEvent(GameEvent):
    """
    Event broadcast when a player's riichi is accepted, with the declarer's score after its deposit and the riichi
    sticks on the table with it.
    """

    type: Literal[EventType.RIICHI_DECLARED] = EventType.RIICHI_DECLARED
    target: EventTarget = _BROADCAST
    seat: int
    score: int
    riichi_sticks: int


class DoraRevealedEvent(GameEvent):
    """
    Event broadcast when a new dora indicator is revealed (after kan).
    """

    type: Literal[EventType.DORA_REVEALED] = EventType.DORA_REVEALED
    target: EventTarget = _BROADCAST
    tile_id: int


class GameStartedEvent(GameEvent):
    """
    Event broadcast to all players when the game starts: the table's rules and first dealer.

    Who sits where, and the game's id, are the caller's.

    riichi_stick_value is the setting a client consumes: what each stick a winner collects pays it. The replay records
    every setting on its game_started line instead.
    """

    type: Literal[EventType.GAME_STARTED] = EventType.GAME_STARTED
    target: EventTarget = _BROADCAST
    game_type: GameType
    dealer_seat: int
    dealer_dice: tuple[tuple[int, int], tuple[int, int]]
    riichi_stick_value: int


class RoundStartedEvent(GameEvent):
    """
    Event sent to each player when a new round starts.

    round_number counts every deal of the game, repeats included; round_in_wind names the round within its wind, from 1
    ("East 1"). tiles_remaining is the live wall after the deal.
    """

    type: Literal[EventType.ROUND_STARTED] = EventType.ROUND_STARTED
    seat: int
    round_wind: WindName
    round_number: int
    round_in_wind: int
    dealer_seat: int
    current_player_seat: int
    dora_indicators: list[int]
    honba_sticks: int
    riichi_sticks: int
    my_tiles: list[int]
    players: list[PlayerView]
    dice: tuple[int, int]
    tiles_remaining: int


class GameEndedEvent(GameEvent):
    """
    Event sent when the entire game ends.
    """

    type: Literal[EventType.GAME_END] = EventType.GAME_END
    target: EventTarget = _BROADCAST
    winner_seat: int
    standings: list[PlayerStanding]
    leftover_riichi_bonus: int
    leftover_riichi_sticks: int
    num_rounds: int
    end_cause: GameEndCause


class FuritenEvent(GameEvent):
    """
    Event sent to a player when their furiten state changes.
    """

    type: Literal[EventType.FURITEN] = EventType.FURITEN
    is_furiten: bool


Event = (
    DrawEvent
    | DrawNoticeEvent
    | DiscardEvent
    | MeldEvent
    | RoundEndEvent
    | RiichiDeclaredEvent
    | DoraRevealedEvent
    | GameStartedEvent
    | RoundStartedEvent
    | GameEndedEvent
    | FuritenEvent
)
