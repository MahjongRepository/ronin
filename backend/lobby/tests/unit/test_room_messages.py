"""Tests for lobby WebSocket message parsing."""

import pytest
from pydantic import ValidationError

from lobby.rooms.messages import (
    LobbyChatMessage,
    LobbyLeaveRoomMessage,
    LobbyPingMessage,
    LobbySetReadyMessage,
    LobbyStartGameMessage,
    parse_lobby_message,
)


class TestParseLobbyMessage:
    def test_parse_set_ready(self):
        msg = parse_lobby_message('{"type": "set_ready", "ready": true}')
        assert isinstance(msg, LobbySetReadyMessage)
        assert msg.ready is True

    def test_parse_chat(self):
        msg = parse_lobby_message('{"type": "chat", "text": "hello"}')
        assert isinstance(msg, LobbyChatMessage)
        assert msg.text == "hello"

    def test_parse_leave_room(self):
        msg = parse_lobby_message('{"type": "leave_room"}')
        assert isinstance(msg, LobbyLeaveRoomMessage)

    def test_parse_ping(self):
        msg = parse_lobby_message('{"type": "ping"}')
        assert isinstance(msg, LobbyPingMessage)

    def test_parse_start_game(self):
        msg = parse_lobby_message('{"type": "start_game"}')
        assert isinstance(msg, LobbyStartGameMessage)

    def test_reject_unknown_type(self):
        with pytest.raises(ValidationError, match="type"):
            parse_lobby_message('{"type": "unknown"}')

    def test_reject_oversized_message(self):
        # Build a raw JSON string that exceeds 4096 bytes using set_ready padding
        # The set_ready message is small, so we pad the JSON to exceed the limit
        padding = "a" * 4097
        raw = f'{{"type": "set_ready", "ready": true, "x": "{padding}"}}'
        with pytest.raises(ValueError, match="Message too large"):
            parse_lobby_message(raw)

    def test_multibyte_character_size_check(self):
        """CJK characters are 3 bytes in UTF-8; size check uses byte length."""
        # Each CJK char is 3 bytes. ~1300 chars = ~3900 bytes, should be fine.
        text = "\u4e00" * 1000  # 3000 bytes
        raw = f'{{"type": "chat", "text": "{text}"}}'
        msg = parse_lobby_message(raw)
        assert isinstance(msg, LobbyChatMessage)

    def test_multibyte_exceeds_limit(self):
        """Enough CJK characters to exceed 4096 byte limit."""
        text = "\u4e00" * 1400  # 4200 bytes
        raw = f'{{"type": "chat", "text": "{text}"}}'
        with pytest.raises(ValueError, match="Message too large"):
            parse_lobby_message(raw)

    def test_chat_rejects_control_characters(self):
        with pytest.raises(ValidationError, match="control characters"):
            parse_lobby_message('{"type": "chat", "text": "hello\\u0000world"}')

    def test_chat_rejects_empty_text(self):
        with pytest.raises(ValidationError, match="at least 1 character"):
            parse_lobby_message('{"type": "chat", "text": ""}')

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="Expecting value"):
            parse_lobby_message("not json")
