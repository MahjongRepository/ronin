from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from game.logic.enums import GameAction


class ClientMessageType(str, Enum):
    JOIN_GAME = "join_game"
    LEAVE_GAME = "leave_game"
    GAME_ACTION = "game_action"
    CHAT = "chat"
    PING = "ping"


class SessionMessageType(str, Enum):
    GAME_JOINED = "game_joined"
    GAME_LEFT = "game_left"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    CHAT = "chat"
    ERROR = "session_error"
    PONG = "pong"


class SessionErrorCode(str, Enum):
    ALREADY_IN_GAME = "already_in_game"
    GAME_NOT_FOUND = "game_not_found"
    GAME_STARTED = "game_started"
    GAME_FULL = "game_full"
    NAME_TAKEN = "name_taken"
    NOT_IN_GAME = "not_in_game"
    INVALID_MESSAGE = "invalid_message"
    ACTION_FAILED = "action_failed"


class JoinGameMessage(BaseModel):
    type: Literal[ClientMessageType.JOIN_GAME] = ClientMessageType.JOIN_GAME
    game_id: str = Field(min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    player_name: str = Field(min_length=1, max_length=50)


class LeaveGameMessage(BaseModel):
    type: Literal[ClientMessageType.LEAVE_GAME] = ClientMessageType.LEAVE_GAME


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
    JoinGameMessage | LeaveGameMessage | GameActionMessage | ChatMessage | PingMessage,
    Field(discriminator="type"),
]


class GameJoinedMessage(BaseModel):
    type: Literal[SessionMessageType.GAME_JOINED] = SessionMessageType.GAME_JOINED
    game_id: str
    players: list[str]


class GameLeftMessage(BaseModel):
    type: Literal[SessionMessageType.GAME_LEFT] = SessionMessageType.GAME_LEFT


class PlayerJoinedMessage(BaseModel):
    type: Literal[SessionMessageType.PLAYER_JOINED] = SessionMessageType.PLAYER_JOINED
    player_name: str


class PlayerLeftMessage(BaseModel):
    type: Literal[SessionMessageType.PLAYER_LEFT] = SessionMessageType.PLAYER_LEFT
    player_name: str


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
