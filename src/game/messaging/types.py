from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ClientMessageType(str, Enum):
    JOIN_GAME = "join_game"
    LEAVE_GAME = "leave_game"
    GAME_ACTION = "game_action"
    CHAT = "chat"


class ServerMessageType(str, Enum):
    GAME_JOINED = "game_joined"
    GAME_LEFT = "game_left"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STATE = "game_state"
    GAME_EVENT = "game_event"
    CHAT = "chat"
    ERROR = "error"


class JoinGameMessage(BaseModel):
    type: Literal[ClientMessageType.JOIN_GAME] = ClientMessageType.JOIN_GAME
    game_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    player_name: str = Field(min_length=1, max_length=50)


class LeaveGameMessage(BaseModel):
    type: Literal[ClientMessageType.LEAVE_GAME] = ClientMessageType.LEAVE_GAME


class GameActionMessage(BaseModel):
    type: Literal[ClientMessageType.GAME_ACTION] = ClientMessageType.GAME_ACTION
    action: str = Field(min_length=1, max_length=100)
    data: dict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    type: Literal[ClientMessageType.CHAT] = ClientMessageType.CHAT
    text: str = Field(min_length=1, max_length=1000)


ClientMessage = Annotated[
    JoinGameMessage | LeaveGameMessage | GameActionMessage | ChatMessage,
    Field(discriminator="type"),
]


class GameJoinedMessage(BaseModel):
    type: Literal[ServerMessageType.GAME_JOINED] = ServerMessageType.GAME_JOINED
    game_id: str
    players: list[str]


class GameLeftMessage(BaseModel):
    type: Literal[ServerMessageType.GAME_LEFT] = ServerMessageType.GAME_LEFT


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
    GameJoinedMessage
    | GameLeftMessage
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
