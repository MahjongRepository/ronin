from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from game.logic.enums import KanType
from game.logic.tiles import NUM_TILES
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.wire.enums import SeatControlReason
from game.wire.keys import WireKey


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


_TILE_ID_FIELD = Field(ge=0, lt=NUM_TILES)


class GameActionMessage(BaseModel, frozen=True):
    """
    A game action: every one names its action (`WireKey.ACTION`) and echoes the id of the wait it answers
    (`WireKey.WAIT_ID`), as the server last sent it.
    """

    message_type: Literal[WireClientMessageType.GAME_ACTION] = WireClientMessageType.GAME_ACTION
    action: WireGameAction
    wait_id: int = Field(ge=0, strict=True)


class DiscardMessage(GameActionMessage):
    action: Literal[WireGameAction.DISCARD] = WireGameAction.DISCARD
    tile_id: int = _TILE_ID_FIELD


class RiichiMessage(GameActionMessage):
    action: Literal[WireGameAction.DECLARE_RIICHI] = WireGameAction.DECLARE_RIICHI
    tile_id: int = _TILE_ID_FIELD


class PonMessage(GameActionMessage):
    action: Literal[WireGameAction.CALL_PON] = WireGameAction.CALL_PON
    tile_id: int = _TILE_ID_FIELD


class ChiMessage(GameActionMessage):
    action: Literal[WireGameAction.CALL_CHI] = WireGameAction.CALL_CHI
    tile_id: int = _TILE_ID_FIELD
    sequence_tiles: tuple[
        Annotated[int, Field(ge=0, lt=NUM_TILES)],
        Annotated[int, Field(ge=0, lt=NUM_TILES)],
    ]


class KanMessage(GameActionMessage):
    action: Literal[WireGameAction.CALL_KAN] = WireGameAction.CALL_KAN
    tile_id: int = _TILE_ID_FIELD
    kan_type: KanType


class NoDataActionMessage(GameActionMessage):
    action: Literal[
        WireGameAction.DECLARE_TSUMO,
        WireGameAction.CALL_RON,
        WireGameAction.CALL_KYUUSHU,
        WireGameAction.PASS,
        WireGameAction.CONFIRM_ROUND,
    ]


_AnyGameActionMessage = Annotated[
    DiscardMessage | RiichiMessage | PonMessage | ChiMessage | KanMessage | NoDataActionMessage,
    Field(discriminator="action"),
]


class ReconnectMessage(BaseModel):
    message_type: Literal[WireClientMessageType.RECONNECT] = WireClientMessageType.RECONNECT
    game_ticket: str = Field(min_length=1, max_length=2000)


class JoinGameMessage(BaseModel):
    message_type: Literal[WireClientMessageType.JOIN_GAME] = WireClientMessageType.JOIN_GAME
    game_ticket: str = Field(min_length=1, max_length=2000)


class ResyncMessage(BaseModel):
    """A seat's request, on the connection that holds it, for its snapshot and
    its pending wait again: its client lost step with the server's messages and
    drops everything until the snapshot arrives."""

    message_type: Literal[WireClientMessageType.RESYNC] = WireClientMessageType.RESYNC


ClientMessage = GameActionMessage | ReconnectMessage | JoinGameMessage | ResyncMessage


class ErrorMessage(BaseModel):
    """
    A session error.

    A rate limit names the wait id (`WireKey.WAIT_ID`) the refused game action echoed, when it had a readable one, so
    the client matches the refusal to its own request and never to a newer wait.
    """

    type: Literal[SessionMessageType.ERROR] = SessionMessageType.ERROR
    code: SessionErrorCode
    message: str
    wait_id: int | None = None

    def payload(self) -> dict[int, Any]:
        """
        Return the wire-format dict, without a wait id it does not name.
        """
        payload: dict[int, Any] = {
            WireKey.SESSION_TYPE: self.type,
            WireKey.SESSION_ERROR_CODE: self.code,
            WireKey.SESSION_ERROR_MESSAGE: self.message,
        }
        if self.wait_id is not None:
            payload[WireKey.WAIT_ID] = self.wait_id

        return payload


def refused_wait_id(data: dict[int, Any]) -> int | None:
    """
    Return the wait id a decoded game action frame echoes, or None for any other frame or an id that is not a wait id.
    """
    wait_id = data.get(WireKey.WAIT_ID)
    is_game_action = data.get(WireKey.EVENT_TYPE) == WireClientMessageType.GAME_ACTION
    return wait_id if is_game_action and type(wait_id) is int and wait_id >= 0 else None


class TimerSettings(BaseModel):
    """
    Describe a seat's pacing (seconds): the shared turn/call base time, current and full per-hand bank, round advance
    timeout per result shown and game start confirmation timeout.
    """

    base_turn_seconds: float
    bank_seconds: float
    max_bank_seconds: float
    round_advance_timeout_seconds: float
    game_start_confirm_seconds: float

    def payload(self) -> dict[int, Any]:
        return {
            WireKey.BASE_TURN_SECONDS: self.base_turn_seconds,
            WireKey.BANK_SECONDS: self.bank_seconds,
            WireKey.MAX_BANK_SECONDS: self.max_bank_seconds,
            WireKey.ROUND_ADVANCE_TIMEOUT: self.round_advance_timeout_seconds,
            WireKey.GAME_START_CONFIRM: self.game_start_confirm_seconds,
        }


class GameJoinedMessage(BaseModel):
    """
    The answer to an accepted JOIN_GAME, sent to the joining connection alone once it holds the participant's seat,
    ahead of anything the game sends it, so the client is admitted by the server's word rather than by inference.

    It names how long the pending game waits for its players before it starts without them
    (`WireKey.PENDING_GAME_TIMEOUT`, seconds), the longest the server can then stay silent before its game start, so the
    client never takes that wait for a lost connection.
    """

    type: Literal[SessionMessageType.GAME_JOINED] = SessionMessageType.GAME_JOINED
    pending_game_timeout_seconds: float

    def payload(self) -> dict[int, Any]:
        """
        Return the wire-format dict.
        """
        return {
            WireKey.SESSION_TYPE: self.type,
            WireKey.PENDING_GAME_TIMEOUT: self.pending_game_timeout_seconds,
        }


class SeatControlMessage(BaseModel):
    """
    Broadcast to the game's connected players when a participant's seat changes hands, as the replay's seat control
    line records it: an AI player stands in for the participant (reason says why), or, without a reason, the
    participant takes the seat back.
    """

    type: Literal[SessionMessageType.SEAT_CONTROL] = SessionMessageType.SEAT_CONTROL
    seat: int
    reason: SeatControlReason | None = None

    def payload(self) -> dict[int, Any]:
        payload: dict[int, Any] = {WireKey.SESSION_TYPE: self.type, WireKey.SEAT: self.seat}
        if self.reason is not None:
            payload[WireKey.SEAT_CONTROL_REASON] = self.reason

        return payload


_NonGameMessage = Annotated[
    ReconnectMessage | JoinGameMessage | ResyncMessage,
    Field(discriminator="message_type"),
]

_non_game_adapter = TypeAdapter(_NonGameMessage)
_game_action_adapter = TypeAdapter(_AnyGameActionMessage)


def parse_client_message(data: dict[int, Any]) -> ClientMessage:
    """
    Parse a raw dict into a typed ClientMessage.

    Game action messages use message type and action discriminators, so they are routed to a separate adapter.
    """
    message_type = data.get(WireKey.EVENT_TYPE)
    if message_type == WireClientMessageType.GAME_ACTION:
        return _game_action_adapter.validate_python(
            {
                "message_type": message_type,
                "action": data.get(WireKey.ACTION),
                "wait_id": data.get(WireKey.WAIT_ID),
                "tile_id": data.get(WireKey.TILE_ID),
                "sequence_tiles": data.get(WireKey.SEQUENCE_TILES),
                "kan_type": data.get(WireKey.ACTION_KAN_TYPE),
            }
        )

    return _non_game_adapter.validate_python(
        {
            "message_type": message_type,
            "game_ticket": data.get(WireKey.GAME_TICKET),
        }
    )
