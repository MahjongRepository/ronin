from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from game.logic.enums import KanType
from game.logic.tiles import NUM_TILES
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.wire.enums import SeatControlReason


class SessionMessageType(StrEnum):
    ERROR = "session_error"
    GAME_JOINED = "game_joined"
    GAME_RECONNECTED = "game_reconnected"
    SEAT_CONTROL = "seat_control"


class SessionErrorCode(StrEnum):
    ALREADY_IN_GAME = "already_in_game"
    NOT_IN_GAME = "not_in_game"
    GAME_NOT_STARTED = "game_not_started"
    INVALID_MESSAGE = "invalid_message"
    INTERNAL_ERROR = "internal_error"
    RECONNECT_NO_SESSION = "reconnect_no_session"
    RECONNECT_GAME_MISMATCH = "reconnect_game_mismatch"
    RECONNECT_RETRY_LATER = "reconnect_retry_later"
    RECONNECT_ALREADY_ACTIVE = "reconnect_already_active"
    INVALID_TICKET = "invalid_ticket"
    JOIN_GAME_NOT_FOUND = "join_game_not_found"
    JOIN_GAME_ALREADY_STARTED = "join_game_already_started"
    JOIN_GAME_NO_SESSION = "join_game_no_session"
    RATE_LIMITED = "rate_limited"


_TILE_ID_FIELD = Field(ge=0, lt=NUM_TILES, validation_alias="ti")


class GameActionMessage(BaseModel, frozen=True):
    """
    A game action: every one names its action (`a`) and echoes the id of the wait it answers (`wi`), as the server last
    sent it.
    """

    t: Literal[WireClientMessageType.GAME_ACTION] = WireClientMessageType.GAME_ACTION
    a: WireGameAction
    wait_id: int = Field(ge=0, strict=True, validation_alias="wi")


class DiscardMessage(GameActionMessage):
    a: Literal[WireGameAction.DISCARD] = WireGameAction.DISCARD
    tile_id: int = _TILE_ID_FIELD


class RiichiMessage(GameActionMessage):
    a: Literal[WireGameAction.DECLARE_RIICHI] = WireGameAction.DECLARE_RIICHI
    tile_id: int = _TILE_ID_FIELD


class PonMessage(GameActionMessage):
    a: Literal[WireGameAction.CALL_PON] = WireGameAction.CALL_PON
    tile_id: int = _TILE_ID_FIELD


class ChiMessage(GameActionMessage):
    a: Literal[WireGameAction.CALL_CHI] = WireGameAction.CALL_CHI
    tile_id: int = _TILE_ID_FIELD
    sequence_tiles: tuple[
        Annotated[int, Field(ge=0, lt=NUM_TILES)],
        Annotated[int, Field(ge=0, lt=NUM_TILES)],
    ]


class KanMessage(GameActionMessage):
    a: Literal[WireGameAction.CALL_KAN] = WireGameAction.CALL_KAN
    tile_id: int = _TILE_ID_FIELD
    kan_type: KanType


class NoDataActionMessage(GameActionMessage):
    a: Literal[
        WireGameAction.DECLARE_TSUMO,
        WireGameAction.CALL_RON,
        WireGameAction.CALL_KYUUSHU,
        WireGameAction.PASS,
        WireGameAction.CONFIRM_ROUND,
    ]


_AnyGameActionMessage = Annotated[
    DiscardMessage | RiichiMessage | PonMessage | ChiMessage | KanMessage | NoDataActionMessage,
    Field(discriminator="a"),
]


class ReconnectMessage(BaseModel):
    t: Literal[WireClientMessageType.RECONNECT] = WireClientMessageType.RECONNECT
    game_ticket: str = Field(min_length=1, max_length=2000)


class JoinGameMessage(BaseModel):
    t: Literal[WireClientMessageType.JOIN_GAME] = WireClientMessageType.JOIN_GAME
    game_ticket: str = Field(min_length=1, max_length=2000)


class ResyncMessage(BaseModel):
    """
    A seat's request, on the connection that holds it, for its snapshot and its pending wait again: its client lost step
    with the server's messages and drops everything until the snapshot arrives.
    """

    t: Literal[WireClientMessageType.RESYNC] = WireClientMessageType.RESYNC


ClientMessage = GameActionMessage | ReconnectMessage | JoinGameMessage | ResyncMessage


class ErrorMessage(BaseModel):
    """
    A session error.

    A rate limit names the wait id (`wi`) the refused game action echoed, when it had a readable one, so the client
    matches the refusal to its own request and never to a newer wait.
    """

    type: Literal[SessionMessageType.ERROR] = SessionMessageType.ERROR
    code: SessionErrorCode
    message: str
    wait_id: int | None = Field(default=None, serialization_alias="wi")

    def payload(self) -> dict[str, Any]:
        """
        Return the wire-format dict, without a wait id it does not name.
        """
        return self.model_dump(by_alias=True, exclude_none=True)


def refused_wait_id(data: dict[str, Any]) -> int | None:
    """
    Return the wait id a decoded game action frame echoes, or None for any other frame or an id that is not a wait id.
    """
    wait_id = data.get("wi")
    is_game_action = data.get("t") == WireClientMessageType.GAME_ACTION
    return wait_id if is_game_action and type(wait_id) is int and wait_id >= 0 else None


class TimerSettings(BaseModel):
    """
    Describe a seat's pacing (seconds): the shared turn/call base time, current and full per-hand bank, round advance
    timeout per result shown and game start pause.
    """

    base_turn_seconds: float = Field(serialization_alias="tb")
    bank_seconds: float = Field(serialization_alias="bk")
    max_bank_seconds: float = Field(serialization_alias="mb")
    round_advance_timeout_seconds: float = Field(serialization_alias="ra")
    game_start_pause_seconds: float = Field(serialization_alias="gp")


class GameJoinedMessage(BaseModel):
    """
    The answer to an accepted JOIN_GAME, sent to the joining connection alone once it holds the participant's seat,
    ahead of anything the game sends it, so the client is admitted by the server's word rather than by inference.

    It names how long the pending game waits for its players before it starts without them (`pt`, seconds), the longest
    the server can then stay silent before its game start, so the client never takes that wait for a lost connection.
    """

    type: Literal[SessionMessageType.GAME_JOINED] = SessionMessageType.GAME_JOINED
    pending_game_timeout_seconds: float = Field(serialization_alias="pt")

    def payload(self) -> dict[str, Any]:
        """
        Return the wire-format dict.
        """
        return self.model_dump(by_alias=True)


class SeatControlMessage(BaseModel):
    """
    Broadcast to the game's connected players when a participant's seat changes hands, as the replay's seat control
    line records it: an AI player stands in for the participant (reason says why), or, without a reason, the
    participant takes the seat back.
    """

    type: Literal[SessionMessageType.SEAT_CONTROL] = SessionMessageType.SEAT_CONTROL
    seat: int = Field(serialization_alias="s")
    reason: SeatControlReason | None = Field(default=None, serialization_alias="r")


_NonGameMessage = Annotated[
    ReconnectMessage | JoinGameMessage | ResyncMessage,
    Field(discriminator="t"),
]

_non_game_adapter = TypeAdapter(_NonGameMessage)
_game_action_adapter = TypeAdapter(_AnyGameActionMessage)


def parse_client_message(data: dict[str, Any]) -> ClientMessage:
    """
    Parse a raw dict into a typed ClientMessage.

    Game action messages use a two-level discriminator (t then a), so they are routed to a separate adapter.
    """
    if data.get("t") == WireClientMessageType.GAME_ACTION:
        return _game_action_adapter.validate_python(data)

    return _non_game_adapter.validate_python(data)
