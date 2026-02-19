from game.logic.enums import MeldViewType
from game.logic.events import (
    BroadcastTarget,
    DiscardEvent,
    DrawEvent,
    EventType,
    MeldEvent,
    RoundEndEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.types import (
    AvailableActionItem,
    DoubleRonResult,
    DoubleRonWinner,
    HandResultInfo,
    RonResult,
    TsumoResult,
)
from game.messaging.event_payload import (
    EVENT_TYPE_INT,
    service_event_payload,
    shape_call_prompt_payload,
)
from shared.lib.melds import EVENT_TYPE_MELD, decode_meld_compact


class TestEventTypeIntExhaustiveness:
    """Verify EVENT_TYPE_INT covers every EventType member."""

    def test_all_event_types_mapped(self):
        missing = set(EventType) - set(EVENT_TYPE_INT)
        assert not missing, f"EVENT_TYPE_INT missing entries for: {missing}"

    def test_no_duplicate_integer_values(self):
        values = list(EVENT_TYPE_INT.values())
        assert len(values) == len(set(values)), "EVENT_TYPE_INT has duplicate integer values"


class TestServiceEventPayload:
    """Tests for centralized event payload shaping."""

    def test_broadcast_event_payload(self):
        event = ServiceEvent(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, is_riichi=True),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        assert payload["t"] == EVENT_TYPE_INT[EventType.DISCARD]
        assert payload["seat"] == 0
        assert payload["tile_id"] == 10
        assert "is_tsumogiri" not in payload
        assert payload["is_riichi"] is True
        # internal fields excluded
        assert "target" not in payload or payload.get("target") is None

    def test_seat_target_event_payload(self):
        event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(seat=1, tile_id=42, target="seat_1"),
            target=SeatTarget(seat=1),
        )
        payload = service_event_payload(event)

        assert payload["t"] == EVENT_TYPE_INT[EventType.DRAW]
        assert payload["seat"] == 1
        assert payload["tile_id"] == 42
        assert "available_actions" not in payload

    def test_draw_with_available_actions_included(self):
        """Non-empty available_actions are included in draw wire payloads."""
        event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                seat=0,
                tile_id=10,
                target="seat_0",
                available_actions=[AvailableActionItem(action="discard", tiles=[10])],
            ),
            target=SeatTarget(seat=0),
        )
        payload = service_event_payload(event)

        assert len(payload["available_actions"]) == 1

    def test_discard_false_flags_omitted(self):
        """False boolean flags are omitted from discard wire payloads."""
        event = ServiceEvent(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        assert "is_tsumogiri" not in payload
        assert "is_riichi" not in payload
        assert set(payload.keys()) == {"t", "seat", "tile_id"}

    def test_discard_true_flags_included(self):
        """True boolean flags are included in discard wire payloads."""
        event = ServiceEvent(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, is_tsumogiri=True, is_riichi=True),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        assert payload["is_tsumogiri"] is True
        assert payload["is_riichi"] is True


class TestShapeCallPromptPayload:
    """Tests for call prompt wire payload shaping."""

    def test_ron_prompt_drops_callers_keeps_caller_seat(self):
        payload = {
            "type": "call_prompt",
            "call_type": "ron",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [0],
        }
        result = shape_call_prompt_payload(payload)

        assert "callers" not in result
        assert result == {
            "type": "call_prompt",
            "call_type": "ron",
            "tile_id": 42,
            "from_seat": 1,
            "caller_seat": 0,
        }

    def test_chankan_prompt_drops_callers_keeps_caller_seat(self):
        payload = {
            "type": "call_prompt",
            "call_type": "chankan",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [3],
        }
        result = shape_call_prompt_payload(payload)

        assert "callers" not in result
        assert result["caller_seat"] == 3

    def test_meld_prompt_replaces_callers_with_available_calls(self):
        payload = {
            "type": "call_prompt",
            "call_type": "meld",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [
                {"seat": 0, "call_type": "pon", "options": None},
            ],
        }
        result = shape_call_prompt_payload(payload)

        assert "callers" not in result
        assert result["caller_seat"] == 0
        assert result["available_calls"] == [{"call_type": "pon"}]

    def test_meld_prompt_preserves_chi_options(self):
        payload = {
            "type": "call_prompt",
            "call_type": "meld",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [
                {"seat": 0, "call_type": "chi", "options": [[40, 44]]},
            ],
        }
        result = shape_call_prompt_payload(payload)

        assert result["caller_seat"] == 0
        assert result["available_calls"] == [
            {"call_type": "chi", "options": [[40, 44]]},
        ]

    def test_unknown_call_type_returns_payload_unchanged(self):
        payload = {
            "type": "call_prompt",
            "call_type": "unknown",
            "tile_id": 42,
            "from_seat": 1,
            "callers": [0],
        }
        result = shape_call_prompt_payload(payload)

        assert result == payload
        assert result["callers"] == [0]

    def test_meld_prompt_multiple_call_types(self):
        payload = {
            "type": "call_prompt",
            "call_type": "meld",
            "tile_id": 55,
            "from_seat": 3,
            "callers": [
                {"seat": 0, "call_type": "pon", "options": None},
                {"seat": 0, "call_type": "chi", "options": [[57, 63]]},
            ],
        }
        result = shape_call_prompt_payload(payload)

        assert "callers" not in result
        assert result["caller_seat"] == 0
        assert result["available_calls"] == [
            {"call_type": "pon"},
            {"call_type": "chi", "options": [[57, 63]]},
        ]


class TestMeldEventPayload:
    """Tests for MeldEvent compact wire payload."""

    def test_meld_event_produces_compact_format(self):
        """MeldEvent is serialized as compact {"t": 0, "m": <IMME_int>}."""
        event = ServiceEvent(
            event=EventType.MELD,
            data=MeldEvent(
                meld_type=MeldViewType.ADDED_KAN,
                caller_seat=0,
                tile_ids=[4, 5, 6, 7],
                called_tile_id=5,
                from_seat=2,
            ),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        assert payload["t"] == EVENT_TYPE_MELD
        assert "m" in payload
        assert set(payload.keys()) == {"t", "m"}

        # Round-trip: decode the IMME value and verify fields
        decoded = decode_meld_compact(payload["m"])
        assert decoded["meld_type"] == "added_kan"
        assert decoded["caller_seat"] == 0
        assert decoded["tile_ids"] == [4, 5, 6, 7]
        assert decoded["called_tile_id"] == 5
        assert decoded["from_seat"] == 2


_HAND_RESULT = HandResultInfo(han=1, fu=30, yaku=[])
_SCORES = {0: 25000, 1: 25000, 2: 25000, 3: 25000}


class TestRoundEndWinFieldStripping:
    """Tests that pao_seat and ura_dora_indicators are omitted when None."""

    def test_tsumo_none_fields_omitted(self):
        """Tsumo result omits pao_seat and ura_dora_indicators when None."""
        event = ServiceEvent(
            event=EventType.ROUND_END,
            data=RoundEndEvent(
                target="all",
                result=TsumoResult(
                    winner_seat=0,
                    hand_result=_HAND_RESULT,
                    scores=_SCORES,
                    score_changes=_SCORES,
                    riichi_sticks_collected=0,
                    closed_tiles=[],
                    melds=[],
                    win_tile=1,
                ),
            ),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        assert "result" not in payload
        assert payload["result_type"] == "tsumo"
        assert "pao_seat" not in payload
        assert "ura_dora_indicators" not in payload

    def test_tsumo_present_fields_kept(self):
        """Tsumo result keeps pao_seat and ura_dora_indicators when set."""
        event = ServiceEvent(
            event=EventType.ROUND_END,
            data=RoundEndEvent(
                target="all",
                result=TsumoResult(
                    winner_seat=0,
                    hand_result=_HAND_RESULT,
                    scores=_SCORES,
                    score_changes=_SCORES,
                    riichi_sticks_collected=0,
                    closed_tiles=[],
                    melds=[],
                    win_tile=1,
                    pao_seat=2,
                    ura_dora_indicators=[10],
                ),
            ),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        assert payload["pao_seat"] == 2
        assert payload["ura_dora_indicators"] == [10]

    def test_ron_none_fields_omitted(self):
        """Ron result omits pao_seat and ura_dora_indicators when None."""
        event = ServiceEvent(
            event=EventType.ROUND_END,
            data=RoundEndEvent(
                target="all",
                result=RonResult(
                    winner_seat=0,
                    loser_seat=1,
                    winning_tile=10,
                    hand_result=_HAND_RESULT,
                    scores=_SCORES,
                    score_changes=_SCORES,
                    riichi_sticks_collected=0,
                    closed_tiles=[],
                    melds=[],
                ),
            ),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        assert "pao_seat" not in payload
        assert "ura_dora_indicators" not in payload

    def test_double_ron_none_fields_omitted(self):
        """Double ron winners omit pao_seat and ura_dora_indicators when None."""
        event = ServiceEvent(
            event=EventType.ROUND_END,
            data=RoundEndEvent(
                target="all",
                result=DoubleRonResult(
                    loser_seat=1,
                    winning_tile=10,
                    winners=[
                        DoubleRonWinner(
                            winner_seat=0,
                            hand_result=_HAND_RESULT,
                            riichi_sticks_collected=0,
                            closed_tiles=[],
                            melds=[],
                        ),
                        DoubleRonWinner(
                            winner_seat=2,
                            hand_result=_HAND_RESULT,
                            riichi_sticks_collected=0,
                            closed_tiles=[],
                            melds=[],
                        ),
                    ],
                    scores=_SCORES,
                    score_changes=_SCORES,
                ),
            ),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        for winner in payload["winners"]:
            assert "pao_seat" not in winner
            assert "ura_dora_indicators" not in winner
