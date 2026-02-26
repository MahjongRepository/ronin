"""Typed client-to-server message models for the lobby WebSocket protocol."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator

_MAX_WS_MESSAGE_SIZE = 4096
_SPACE_ORD = 0x20
_DEL_ORD = 0x7F


class LobbySetReadyMessage(BaseModel):
    type: Literal["set_ready"]
    ready: bool


class LobbyChatMessage(BaseModel):
    type: Literal["chat"]
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if any((ord(c) < _SPACE_ORD and c not in ("\t", "\n", "\r")) or ord(c) == _DEL_ORD for c in v):
            raise ValueError("text must not contain control characters")
        return v


class LobbyLeaveRoomMessage(BaseModel):
    type: Literal["leave_room"]


class LobbyPingMessage(BaseModel):
    type: Literal["ping"]


class LobbyStartGameMessage(BaseModel):
    type: Literal["start_game"]


LobbyClientMessage = Annotated[
    LobbySetReadyMessage | LobbyChatMessage | LobbyLeaveRoomMessage | LobbyPingMessage | LobbyStartGameMessage,
    Field(discriminator="type"),
]

_lobby_message_adapter: TypeAdapter[LobbyClientMessage] = TypeAdapter(LobbyClientMessage)


def parse_lobby_message(
    raw: str,
) -> LobbySetReadyMessage | LobbyChatMessage | LobbyLeaveRoomMessage | LobbyPingMessage | LobbyStartGameMessage:
    """Parse and validate a raw JSON string into a typed lobby message."""
    byte_len = len(raw.encode("utf-8"))
    if byte_len > _MAX_WS_MESSAGE_SIZE:
        raise ValueError(f"Message too large ({byte_len} bytes, max {_MAX_WS_MESSAGE_SIZE})")
    data = json.loads(raw)
    return _lobby_message_adapter.validate_python(data)
