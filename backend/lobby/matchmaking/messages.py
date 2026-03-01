"""Typed client-to-server message models for the matchmaking WebSocket protocol."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, TypeAdapter

_MAX_WS_MESSAGE_SIZE = 4096


class MatchmakingPingMessage(BaseModel):
    type: Literal["ping"]


_matchmaking_message_adapter: TypeAdapter[MatchmakingPingMessage] = TypeAdapter(MatchmakingPingMessage)


def parse_matchmaking_message(raw: str) -> MatchmakingPingMessage:
    """Parse and validate a raw JSON string into a typed matchmaking message."""
    byte_len = len(raw.encode("utf-8"))
    if byte_len > _MAX_WS_MESSAGE_SIZE:
        raise ValueError(f"Message too large ({byte_len} bytes, max {_MAX_WS_MESSAGE_SIZE})")
    data = json.loads(raw)
    return _matchmaking_message_adapter.validate_python(data)
