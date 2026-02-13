from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from game.logic.enums import GameAction
from game.session.room import RoomPlayerInfo


class ClientMessageType(str, Enum):
    JOIN_ROOM = "join_room"
    LEAVE_ROOM = "leave_room"
    SET_READY = "set_ready"
    GAME_ACTION = "game_action"
    CHAT = "chat"
    PING = "ping"


class SessionMessageType(str, Enum):
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


class SessionErrorCode(str, Enum):
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


class JoinRoomMessage(BaseModel):
    type: Literal[ClientMessageType.JOIN_ROOM] = ClientMessageType.JOIN_ROOM
    room_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    player_name: str = Field(min_length=1, max_length=50)
    session_token: str = Field(min_length=1, max_length=100)


class LeaveRoomMessage(BaseModel):
    type: Literal[ClientMessageType.LEAVE_ROOM] = ClientMessageType.LEAVE_ROOM


class SetReadyMessage(BaseModel):
    type: Literal[ClientMessageType.SET_READY] = ClientMessageType.SET_READY
    ready: bool


class GameActionMessage(BaseModel):
    type: Literal[ClientMessageType.GAME_ACTION] = ClientMessageType.GAME_ACTION
    action: GameAction
    data: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    type: Literal[ClientMessageType.CHAT] = ClientMessageType.CHAT
    text: str = Field(min_length=1, max_length=1000)


class PingMessage(BaseModel):
    type: Literal[ClientMessageType.PING] = ClientMessageType.PING


ClientMessage = Annotated[
    JoinRoomMessage | LeaveRoomMessage | SetReadyMessage | GameActionMessage | ChatMessage | PingMessage,
    Field(discriminator="type"),
]


class GameLeftMessage(BaseModel):
    type: Literal[SessionMessageType.GAME_LEFT] = SessionMessageType.GAME_LEFT


class RoomJoinedMessage(BaseModel):
    type: Literal[SessionMessageType.ROOM_JOINED] = SessionMessageType.ROOM_JOINED
    room_id: str
    session_token: str
    players: list[RoomPlayerInfo]
    num_bots: int


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


_client_message_adapter = TypeAdapter(ClientMessage)


def parse_client_message(data: dict[str, Any]) -> ClientMessage:
    return _client_message_adapter.validate_python(data)
