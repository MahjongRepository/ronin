"""Unit tests for matchmaking message parsing."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from lobby.matchmaking.messages import MatchmakingPingMessage, parse_matchmaking_message


class TestParseMatchmakingMessage:
    def test_parse_ping(self):
        msg = parse_matchmaking_message(json.dumps({"type": "ping"}))
        assert isinstance(msg, MatchmakingPingMessage)

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_matchmaking_message("not json")

    def test_unknown_type_raises(self):
        with pytest.raises(ValidationError):
            parse_matchmaking_message(json.dumps({"type": "unknown"}))

    def test_oversized_message_raises(self):
        big = json.dumps({"type": "ping", "padding": "x" * 5000})
        with pytest.raises(ValueError, match="too large"):
            parse_matchmaking_message(big)

    def test_message_at_size_limit_accepted(self):
        base = json.dumps({"type": "ping", "padding": ""})
        padding_needed = 4096 - len(base.encode("utf-8"))
        raw = json.dumps({"type": "ping", "padding": "x" * padding_needed})
        assert len(raw.encode("utf-8")) == 4096
        msg = parse_matchmaking_message(raw)
        assert isinstance(msg, MatchmakingPingMessage)

    def test_message_one_byte_over_limit_rejected(self):
        base = json.dumps({"type": "ping", "padding": ""})
        padding_needed = 4097 - len(base.encode("utf-8"))
        raw = json.dumps({"type": "ping", "padding": "x" * padding_needed})
        assert len(raw.encode("utf-8")) == 4097
        with pytest.raises(ValueError, match="too large"):
            parse_matchmaking_message(raw)
