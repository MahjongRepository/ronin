from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CHAT_MAX_LENGTH = 1000
_MAX_WS_MESSAGE_SIZE = 4096
_SPACE_ORD = 0x20
_DEL_ORD = 0x7F


class LobbyChatMessage(BaseModel):
    type: Literal["chat"]
    text: str = Field(min_length=1, max_length=CHAT_MAX_LENGTH)

    @field_validator("text")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if any((ord(c) < _SPACE_ORD and c not in ("\t", "\n", "\r")) or ord(c) == _DEL_ORD for c in v):
            raise ValueError("text must not contain control characters")

        return v


def decode_client_frame(raw: str) -> object:
    """
    Decode a lobby socket's JSON text frame.

    Raise ``json.JSONDecodeError`` for malformed JSON and a plain ``ValueError`` for a frame over the size limit.
    """
    byte_len = len(raw.encode("utf-8"))
    if byte_len > _MAX_WS_MESSAGE_SIZE:
        raise ValueError(f"Message too large ({byte_len} bytes, max {_MAX_WS_MESSAGE_SIZE})")

    return json.loads(raw)
