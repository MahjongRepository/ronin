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
    def test_parse_lobby_message__when_set_ready__should_return_set_ready_message(self):
        msg = parse_lobby_message('{"type": "set_ready", "ready": true}')
        assert isinstance(msg, LobbySetReadyMessage)
        assert msg.ready is True

    def test_parse_lobby_message__when_chat__should_return_chat_message(self):
        msg = parse_lobby_message('{"type": "chat", "text": "hello"}')
        assert isinstance(msg, LobbyChatMessage)
        assert msg.text == "hello"

    def test_parse_lobby_message__when_leave_room__should_return_leave_room_message(self):
        msg = parse_lobby_message('{"type": "leave_room"}')
        assert isinstance(msg, LobbyLeaveRoomMessage)

    def test_parse_lobby_message__when_ping__should_return_ping_message(self):
        msg = parse_lobby_message('{"type": "ping"}')
        assert isinstance(msg, LobbyPingMessage)

    def test_parse_lobby_message__when_start_game__should_return_start_game_message(self):
        msg = parse_lobby_message('{"type": "start_game"}')
        assert isinstance(msg, LobbyStartGameMessage)

    def test_parse_lobby_message__when_unknown_type__should_reject(self):
        with pytest.raises(ValidationError, match="type"):
            parse_lobby_message('{"type": "unknown"}')

    def test_parse_lobby_message__when_oversized__should_reject(self):
        # Build a raw JSON string that exceeds 4096 bytes using set_ready padding
        # The set_ready message is small, so we pad the JSON to exceed the limit
        padding = "a" * 4097
        raw = f'{{"type": "set_ready", "ready": true, "x": "{padding}"}}'
        with pytest.raises(ValueError, match="Message too large"):
            parse_lobby_message(raw)

    def test_parse_lobby_message__when_multibyte_text_under_limit__should_accept(self):
        # Each CJK char is 3 bytes. ~1300 chars = ~3900 bytes, should be fine.
        text = "\u4e00" * 1000  # 3000 bytes
        raw = f'{{"type": "chat", "text": "{text}"}}'

        msg = parse_lobby_message(raw)
        assert isinstance(msg, LobbyChatMessage)

    def test_parse_lobby_message__when_multibyte_text_over_limit__should_reject(self):
        text = "\u4e00" * 1400  # 4200 bytes
        raw = f'{{"type": "chat", "text": "{text}"}}'
        with pytest.raises(ValueError, match="Message too large"):
            parse_lobby_message(raw)

    def test_parse_lobby_message__when_chat_has_control_characters__should_reject(self):
        with pytest.raises(ValidationError, match="control characters"):
            parse_lobby_message('{"type": "chat", "text": "hello\\u0000world"}')

    def test_parse_lobby_message__when_chat_text_empty__should_reject(self):
        with pytest.raises(ValidationError, match="at least 1 character"):
            parse_lobby_message('{"type": "chat", "text": ""}')

    def test_parse_lobby_message__when_invalid_json__should_raise(self):
        with pytest.raises(ValueError, match="Expecting value"):
            parse_lobby_message("not json")
