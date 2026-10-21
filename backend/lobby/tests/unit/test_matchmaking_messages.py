from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from lobby.matchmaking.messages import MatchmakingPingMessage, parse_matchmaking_message


class TestParseMatchmakingMessage:
    def test_parse_matchmaking_message__when_ping__should_return_ping_message(self):
        msg = parse_matchmaking_message(json.dumps({"type": "ping"}))
        assert isinstance(msg, MatchmakingPingMessage)

    def test_parse_matchmaking_message__when_invalid_json__should_raise(self):
        with pytest.raises(json.JSONDecodeError):
            parse_matchmaking_message("not json")

    def test_parse_matchmaking_message__when_unknown_type__should_raise(self):
        with pytest.raises(ValidationError):
            parse_matchmaking_message(json.dumps({"type": "unknown"}))

    def test_parse_matchmaking_message__when_oversized__should_raise(self):
        big = json.dumps({"type": "ping", "padding": "x" * 5000})
        with pytest.raises(ValueError, match="too large"):
            parse_matchmaking_message(big)

    def test_parse_matchmaking_message__when_at_size_limit__should_accept(self):
        base = json.dumps({"type": "ping", "padding": ""})
        padding_needed = 4096 - len(base.encode("utf-8"))
        raw = json.dumps({"type": "ping", "padding": "x" * padding_needed})
        assert len(raw.encode("utf-8")) == 4096
        msg = parse_matchmaking_message(raw)
        assert isinstance(msg, MatchmakingPingMessage)

    def test_parse_matchmaking_message__when_one_byte_over_limit__should_reject(self):
        base = json.dumps({"type": "ping", "padding": ""})
        padding_needed = 4097 - len(base.encode("utf-8"))
        raw = json.dumps({"type": "ping", "padding": "x" * padding_needed})
        assert len(raw.encode("utf-8")) == 4097
        with pytest.raises(ValueError, match="too large"):
            parse_matchmaking_message(raw)
