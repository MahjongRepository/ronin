import pytest
from pydantic import ValidationError

from game.messaging.types import (
    ChiMessage,
    DiscardMessage,
    ReconnectMessage,
    parse_client_message,
)
from game.messaging.wire_enums import WireClientMessageType, WireGameAction
from game.wire.keys import WireKey


class TestParseClientMessage:
    def test_parse_client_message__when_type_invalid__should_raise(self):
        data = {WireKey.EVENT_TYPE: 99, WireKey.GAME_TICKET: "some-ticket"}
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_chi__should_coerce_sequence_tiles_to_tuple(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.WAIT_ID: 0,
            WireKey.ACTION: WireGameAction.CALL_CHI,
            WireKey.TILE_ID: 40,
            WireKey.SEQUENCE_TILES: [41, 42],
        }
        msg = parse_client_message(data)
        assert isinstance(msg, ChiMessage)
        assert msg.sequence_tiles == (41, 42)

    def test_parse_client_message__when_kan_without_kan_type__should_raise(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.WAIT_ID: 0,
            WireKey.ACTION: WireGameAction.CALL_KAN,
            WireKey.TILE_ID: 8,
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_game_action_missing_required_field__should_raise(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.WAIT_ID: 0,
            WireKey.ACTION: WireGameAction.DISCARD,
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_game_action_invalid__should_raise(self):
        data = {WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION, WireKey.WAIT_ID: 0, WireKey.ACTION: 99}
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestReconnectMessageParsing:
    def test_parse_client_message__when_reconnect__should_return_reconnect_message(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.RECONNECT,
            WireKey.GAME_TICKET: "some-ticket-string",
        }
        msg = parse_client_message(data)
        assert isinstance(msg, ReconnectMessage)
        assert msg.game_ticket == "some-ticket-string"

    def test_parse_client_message__when_reconnect_missing_game_ticket__should_raise(self):
        data = {WireKey.EVENT_TYPE: WireClientMessageType.RECONNECT}
        with pytest.raises(ValidationError):
            parse_client_message(data)


class TestInputValidation:
    @pytest.mark.parametrize("wait_id", [True, "3", 3.0])
    def test_parse_client_message__when_wait_id_is_not_an_int__should_raise(self, wait_id):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.WAIT_ID: wait_id,
            WireKey.ACTION: WireGameAction.PASS,
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    @pytest.mark.parametrize(
        "action_fields",
        [
            {WireKey.ACTION: WireGameAction.DISCARD, WireKey.TILE_ID: True},
            {WireKey.ACTION: WireGameAction.DISCARD, WireKey.TILE_ID: "5"},
            {WireKey.ACTION: WireGameAction.DISCARD, WireKey.TILE_ID: 5.0},
            {WireKey.ACTION: WireGameAction.CALL_CHI, WireKey.TILE_ID: 40, WireKey.SEQUENCE_TILES: [True, 42]},
        ],
    )
    def test_parse_client_message__when_tile_id_is_not_an_int__should_raise(self, action_fields):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.WAIT_ID: 0,
            **action_fields,
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_tile_id_negative__should_raise(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.WAIT_ID: 0,
            WireKey.ACTION: WireGameAction.DISCARD,
            WireKey.TILE_ID: -1,
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_tile_id_above_135__should_raise(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.WAIT_ID: 0,
            WireKey.ACTION: WireGameAction.DISCARD,
            WireKey.TILE_ID: 136,
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_tile_id_is_135__should_return_discard_message(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.WAIT_ID: 0,
            WireKey.ACTION: WireGameAction.DISCARD,
            WireKey.TILE_ID: 135,
        }
        msg = parse_client_message(data)
        assert isinstance(msg, DiscardMessage)
        assert msg.tile_id == 135

    def test_parse_client_message__when_chi_sequence_tile_out_of_range__should_raise(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.GAME_ACTION,
            WireKey.WAIT_ID: 0,
            WireKey.ACTION: WireGameAction.CALL_CHI,
            WireKey.TILE_ID: 0,
            WireKey.SEQUENCE_TILES: [4, 200],
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_join_game_missing_game_ticket__should_raise(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.JOIN_GAME,
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_client_message__when_join_game_ticket_empty__should_raise(self):
        data = {
            WireKey.EVENT_TYPE: WireClientMessageType.JOIN_GAME,
            WireKey.GAME_TICKET: "",
        }
        with pytest.raises(ValidationError):
            parse_client_message(data)
