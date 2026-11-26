from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.chat_messages import LobbyChatMessage, decode_client_frame
from app.rooms.models import TOTAL_SEATS


class LobbySetReadyMessage(BaseModel):
    type: Literal["set_ready"]
    ready: bool


class LobbyLeaveRoomMessage(BaseModel):
    type: Literal["leave_room"]


class LobbyStartGameMessage(BaseModel):
    type: Literal["start_game"]
    strong_bots: int = Field(default=0, ge=0, le=TOTAL_SEATS - 1)


LobbyClientMessage = Annotated[
    LobbySetReadyMessage | LobbyChatMessage | LobbyLeaveRoomMessage | LobbyStartGameMessage,
    Field(discriminator="type"),
]

_lobby_message_adapter: TypeAdapter[LobbyClientMessage] = TypeAdapter(LobbyClientMessage)


def parse_lobby_message(
    raw: str,
) -> LobbySetReadyMessage | LobbyChatMessage | LobbyLeaveRoomMessage | LobbyStartGameMessage:
    """
    Parse and validate a raw JSON string into a typed lobby message.

    Raise ``json.JSONDecodeError`` for malformed JSON, ``ValidationError`` for an invalid message and a plain
    ``ValueError`` for one over the size limit.
    """
    return _lobby_message_adapter.validate_python(decode_client_frame(raw))
