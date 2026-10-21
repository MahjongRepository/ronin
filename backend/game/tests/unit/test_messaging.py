import pytest
from pydantic import ValidationError

from game.messaging.types import (
    ChiMessage,
    DiscardMessage,
    ReconnectMessage,
    parse_client_message,
)
from game.messaging.wire_enums import WireClientMessageType, WireGameAction


class TestParseClientMessage:
    def test_parse_client_message__when_type_invalid__should_raise(self):
        data = {"t": 99, "game_ticket": "some-ticket"}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_chi__should_coerce_sequence_tiles_to_tuple(self):
        data = {
            "t": WireClientMessageType.GAME_ACTION,
            "a": WireGameAction.CALL_CHI,
            "ti": 40,
            "sequence_tiles": [41, 42],
        }
        msg = parse_client_message(data)
        assert isinstance(msg, ChiMessage)
        assert msg.sequence_tiles == (41, 42)

    def test_parse_client_message__when_kan_without_kan_type__should_raise(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.CALL_KAN, "ti": 8}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_game_action_missing_required_field__should_raise(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_game_action_invalid__should_raise(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": 99}
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestReconnectMessageParsing:
    def test_parse_client_message__when_reconnect__should_return_reconnect_message(self):
        data = {
            "t": WireClientMessageType.RECONNECT,
            "game_ticket": "some-ticket-string",
        }
        msg = parse_client_message(data)
        assert isinstance(msg, ReconnectMessage)
        assert msg.game_ticket == "some-ticket-string"

    def test_parse_client_message__when_reconnect_missing_game_ticket__should_raise(self):
        data = {"t": WireClientMessageType.RECONNECT}
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestInputValidation:
    def test_parse_client_message__when_tile_id_negative__should_raise(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": -1}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_tile_id_above_135__should_raise(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": 136}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_tile_id_is_135__should_return_discard_message(self):
        data = {"t": WireClientMessageType.GAME_ACTION, "a": WireGameAction.DISCARD, "ti": 135}
        msg = parse_client_message(data)
        assert isinstance(msg, DiscardMessage)
        assert msg.tile_id == 135

    def test_parse_client_message__when_chi_sequence_tile_out_of_range__should_raise(self):
        data = {
            "t": WireClientMessageType.GAME_ACTION,
            "a": WireGameAction.CALL_CHI,
            "ti": 0,
            "sequence_tiles": [4, 200],
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_join_game_missing_game_ticket__should_raise(self):
        data = {
            "t": WireClientMessageType.JOIN_GAME,
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_join_game_ticket_empty__should_raise(self):
        data = {
            "t": WireClientMessageType.JOIN_GAME,
            "game_ticket": "",
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_chat_text_has_null_byte__should_raise(self):
        data = {
            "t": WireClientMessageType.CHAT,
            "text": "hello\x00world",
        }
        with pytest.raises(ValidationError, match="control characters"):
            parse_client_message(data)

    def test_parse_client_message__when_chat_text_has_tab_and_newline__should_accept_it(self):
        data = {
            "t": WireClientMessageType.CHAT,
            "text": "hello\tworld\nfoo",
        }
        msg = parse_client_message(data)
        assert msg.text == "hello\tworld\nfoo"
