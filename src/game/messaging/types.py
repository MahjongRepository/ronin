from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ClientMessageType(str, Enum):
    JOIN_ROOM = "join_room"
    LEAVE_ROOM = "leave_room"
    GAME_ACTION = "game_action"
    CHAT = "chat"


class ServerMessageType(str, Enum):
    ROOM_JOINED = "room_joined"
    ROOM_LEFT = "room_left"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STATE = "game_state"
    GAME_EVENT = "game_event"
    CHAT = "chat"
    ERROR = "error"


class JoinRoomMessage(BaseModel):
    type: Literal[ClientMessageType.JOIN_ROOM] = ClientMessageType.JOIN_ROOM
    room_id: str
    player_name: str


class LeaveRoomMessage(BaseModel):
    type: Literal[ClientMessageType.LEAVE_ROOM] = ClientMessageType.LEAVE_ROOM


class GameActionMessage(BaseModel):
    type: Literal[ClientMessageType.GAME_ACTION] = ClientMessageType.GAME_ACTION
    action: str
    data: dict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    type: Literal[ClientMessageType.CHAT] = ClientMessageType.CHAT
    text: str


ClientMessage = Annotated[
    JoinRoomMessage | LeaveRoomMessage | GameActionMessage | ChatMessage,
    Field(discriminator="type"),
]


class RoomJoinedMessage(BaseModel):
    type: Literal[ServerMessageType.ROOM_JOINED] = ServerMessageType.ROOM_JOINED
    room_id: str
    players: list[str]


class RoomLeftMessage(BaseModel):
    type: Literal[ServerMessageType.ROOM_LEFT] = ServerMessageType.ROOM_LEFT


class PlayerJoinedMessage(BaseModel):
    type: Literal[ServerMessageType.PLAYER_JOINED] = ServerMessageType.PLAYER_JOINED
    player_name: str


class PlayerLeftMessage(BaseModel):
    type: Literal[ServerMessageType.PLAYER_LEFT] = ServerMessageType.PLAYER_LEFT
    player_name: str


class GameStateMessage(BaseModel):
    type: Literal[ServerMessageType.GAME_STATE] = ServerMessageType.GAME_STATE
    state: dict


class GameEventMessage(BaseModel):
    type: Literal[ServerMessageType.GAME_EVENT] = ServerMessageType.GAME_EVENT
    event: str
    data: dict = Field(default_factory=dict)


class ServerChatMessage(BaseModel):
    type: Literal[ServerMessageType.CHAT] = ServerMessageType.CHAT
    player_name: str
    text: str


class ErrorMessage(BaseModel):
    type: Literal[ServerMessageType.ERROR] = ServerMessageType.ERROR
    code: str
    message: str


ServerMessage = (
    RoomJoinedMessage
    | RoomLeftMessage
    | PlayerJoinedMessage
    | PlayerLeftMessage
    | GameStateMessage
    | GameEventMessage
    | ServerChatMessage
    | ErrorMessage
)


def parse_client_message(data: dict) -> ClientMessage:
    from pydantic import TypeAdapter

    adapter = TypeAdapter(ClientMessage)
    return adapter.validate_python(data)
