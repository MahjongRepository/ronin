from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from game.logic.enums import KanType, WireClientMessageType, WireGameAction
from game.logic.tiles import NUM_TILES

# ASCII control character boundaries for input validation
_SPACE_ORD = 0x20
_DEL_ORD = 0x7F


class RoomPlayerInfo(BaseModel):
    """Player info for room state messages."""

    name: str
    ready: bool


class SessionMessageType(StrEnum):
    GAME_LEFT = "game_left"
    ROOM_JOINED = "room_joined"
    ROOM_LEFT = "room_left"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    PLAYER_READY_CHANGED = "player_ready_changed"
    GAME_STARTING = "game_starting"
    CHAT = "chat"
    ERROR = "session_error"
    PONG = "pong"
    GAME_RECONNECTED = "game_reconnected"
    PLAYER_RECONNECTED = "player_reconnected"


class SessionErrorCode(StrEnum):
    ALREADY_IN_GAME = "already_in_game"
    ALREADY_IN_ROOM = "already_in_room"
    ROOM_NOT_FOUND = "room_not_found"
    ROOM_FULL = "room_full"
    ROOM_TRANSITIONING = "room_transitioning"
    NAME_TAKEN = "name_taken"
    NOT_IN_ROOM = "not_in_room"
    NOT_IN_GAME = "not_in_game"
    GAME_NOT_STARTED = "game_not_started"
    INVALID_MESSAGE = "invalid_message"
    ACTION_FAILED = "action_failed"
    RECONNECT_NO_SESSION = "reconnect_no_session"
    RECONNECT_NO_SEAT = "reconnect_no_seat"
    RECONNECT_GAME_GONE = "reconnect_game_gone"
    RECONNECT_GAME_MISMATCH = "reconnect_game_mismatch"
    RECONNECT_RETRY_LATER = "reconnect_retry_later"
    RECONNECT_IN_ROOM = "reconnect_in_room"
    RECONNECT_ALREADY_ACTIVE = "reconnect_already_active"
    RECONNECT_SNAPSHOT_FAILED = "reconnect_snapshot_failed"
    INVALID_TICKET = "invalid_ticket"


class JoinRoomMessage(BaseModel):
    t: Literal[WireClientMessageType.JOIN_ROOM] = WireClientMessageType.JOIN_ROOM
    room_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    game_ticket: str = Field(min_length=1, max_length=2000)


class LeaveRoomMessage(BaseModel):
    t: Literal[WireClientMessageType.LEAVE_ROOM] = WireClientMessageType.LEAVE_ROOM


class SetReadyMessage(BaseModel):
    t: Literal[WireClientMessageType.SET_READY] = WireClientMessageType.SET_READY
    ready: bool


_TILE_ID_FIELD = Field(ge=0, lt=NUM_TILES, validation_alias="ti")


class DiscardMessage(BaseModel):
    t: Literal[WireClientMessageType.GAME_ACTION] = WireClientMessageType.GAME_ACTION
    a: Literal[WireGameAction.DISCARD] = WireGameAction.DISCARD
    tile_id: int = _TILE_ID_FIELD


class RiichiMessage(BaseModel):
    t: Literal[WireClientMessageType.GAME_ACTION] = WireClientMessageType.GAME_ACTION
    a: Literal[WireGameAction.DECLARE_RIICHI] = WireGameAction.DECLARE_RIICHI
    tile_id: int = _TILE_ID_FIELD


class PonMessage(BaseModel):
    t: Literal[WireClientMessageType.GAME_ACTION] = WireClientMessageType.GAME_ACTION
    a: Literal[WireGameAction.CALL_PON] = WireGameAction.CALL_PON
    tile_id: int = _TILE_ID_FIELD


class ChiMessage(BaseModel):
    t: Literal[WireClientMessageType.GAME_ACTION] = WireClientMessageType.GAME_ACTION
    a: Literal[WireGameAction.CALL_CHI] = WireGameAction.CALL_CHI
    tile_id: int = _TILE_ID_FIELD
    sequence_tiles: tuple[
        Annotated[int, Field(ge=0, lt=NUM_TILES)],
        Annotated[int, Field(ge=0, lt=NUM_TILES)],
    ]


class KanMessage(BaseModel):
    t: Literal[WireClientMessageType.GAME_ACTION] = WireClientMessageType.GAME_ACTION
    a: Literal[WireGameAction.CALL_KAN] = WireGameAction.CALL_KAN
    tile_id: int = _TILE_ID_FIELD
    kan_type: KanType


class NoDataActionMessage(BaseModel):
    t: Literal[WireClientMessageType.GAME_ACTION] = WireClientMessageType.GAME_ACTION
    a: Literal[
        WireGameAction.DECLARE_TSUMO,
        WireGameAction.CALL_RON,
        WireGameAction.CALL_KYUUSHU,
        WireGameAction.PASS,
        WireGameAction.CONFIRM_ROUND,
    ]


GameActionMessage = Annotated[
    DiscardMessage | RiichiMessage | PonMessage | ChiMessage | KanMessage | NoDataActionMessage,
    Field(discriminator="a"),
]


class ChatMessage(BaseModel):
    t: Literal[WireClientMessageType.CHAT] = WireClientMessageType.CHAT
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if any((ord(c) < _SPACE_ORD and c not in ("\t", "\n", "\r")) or ord(c) == _DEL_ORD for c in v):
            raise ValueError("text must not contain control characters")
        return v


class PingMessage(BaseModel):
    t: Literal[WireClientMessageType.PING] = WireClientMessageType.PING


class ReconnectMessage(BaseModel):
    t: Literal[WireClientMessageType.RECONNECT] = WireClientMessageType.RECONNECT
    room_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    game_ticket: str = Field(min_length=1, max_length=2000)


ClientMessage = (
    JoinRoomMessage
    | LeaveRoomMessage
    | SetReadyMessage
    | DiscardMessage
    | RiichiMessage
    | PonMessage
    | ChiMessage
    | KanMessage
    | NoDataActionMessage
    | ChatMessage
    | PingMessage
    | ReconnectMessage
)


class GameLeftMessage(BaseModel):
    type: Literal[SessionMessageType.GAME_LEFT] = SessionMessageType.GAME_LEFT


class RoomJoinedMessage(BaseModel):
    type: Literal[SessionMessageType.ROOM_JOINED] = SessionMessageType.ROOM_JOINED
    room_id: str
    player_name: str
    players: list[RoomPlayerInfo]
    num_ai_players: int


class RoomLeftMessage(BaseModel):
    type: Literal[SessionMessageType.ROOM_LEFT] = SessionMessageType.ROOM_LEFT


class PlayerJoinedMessage(BaseModel):
    type: Literal[SessionMessageType.PLAYER_JOINED] = SessionMessageType.PLAYER_JOINED
    player_name: str


class PlayerLeftMessage(BaseModel):
    type: Literal[SessionMessageType.PLAYER_LEFT] = SessionMessageType.PLAYER_LEFT
    player_name: str


class PlayerReadyChangedMessage(BaseModel):
    type: Literal[SessionMessageType.PLAYER_READY_CHANGED] = SessionMessageType.PLAYER_READY_CHANGED
    player_name: str
    ready: bool


class GameStartingMessage(BaseModel):
    type: Literal[SessionMessageType.GAME_STARTING] = SessionMessageType.GAME_STARTING


class SessionChatMessage(BaseModel):
    type: Literal[SessionMessageType.CHAT] = SessionMessageType.CHAT
    player_name: str
    text: str


class ErrorMessage(BaseModel):
    type: Literal[SessionMessageType.ERROR] = SessionMessageType.ERROR
    code: SessionErrorCode
    message: str


class PongMessage(BaseModel):
    type: Literal[SessionMessageType.PONG] = SessionMessageType.PONG


class PlayerReconnectedMessage(BaseModel):
    """Broadcast to other players when a player reconnects."""

    type: Literal[SessionMessageType.PLAYER_RECONNECTED] = SessionMessageType.PLAYER_RECONNECTED
    player_name: str


_NonGameMessage = Annotated[
    JoinRoomMessage | LeaveRoomMessage | SetReadyMessage | ChatMessage | PingMessage | ReconnectMessage,
    Field(discriminator="t"),
]

_non_game_adapter = TypeAdapter(_NonGameMessage)
_game_action_adapter = TypeAdapter(GameActionMessage)


def parse_client_message(data: dict[str, Any]) -> ClientMessage:
    """Parse a raw dict into a typed ClientMessage.

    Game action messages use a two-level discriminator (t then a),
    so they are routed to a separate adapter.
    """
    if data.get("t") == WireClientMessageType.GAME_ACTION:
        return _game_action_adapter.validate_python(data)
    return _non_game_adapter.validate_python(data)
