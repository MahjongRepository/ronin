from game.logic.enums import MeldViewType, WireCallType, WireMeldCallType, WirePlayerAction, WireRoundResultType
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
    TsumoResult,
)
from game.messaging.compact import decode_discard, decode_draw
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

    def test_discard_produces_packed_integer(self):
        """Discard event produces {"t": 2, "d": <packed_int>}."""
        event = ServiceEvent(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, is_riichi=True),
            target=BroadcastTarget(),
        )
        payload = service_event_payload(event)

        assert payload["t"] == EVENT_TYPE_INT[EventType.DISCARD]
        assert set(payload.keys()) == {"t", "d"}
        seat, tile_id, is_tsumogiri, is_riichi = decode_discard(payload["d"])
        assert seat == 0
        assert tile_id == 10
        assert is_tsumogiri is False
        assert is_riichi is True

    def test_draw_produces_packed_integer(self):
        """Draw event produces {"t": 1, "d": <packed_int>}."""
        event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(seat=1, tile_id=42, target="seat_1"),
            target=SeatTarget(seat=1),
        )
        payload = service_event_payload(event)

        assert payload["t"] == EVENT_TYPE_INT[EventType.DRAW]
        assert set(payload.keys()) == {"t", "d"}
        seat, tile_id = decode_draw(payload["d"])
        assert seat == 1
        assert tile_id == 42

    def test_draw_with_available_actions_included(self):
        """Non-empty available_actions are included as 'aa' with compact keys."""
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

        assert "aa" in payload
        assert len(payload["aa"]) == 1
        assert payload["aa"][0] == {"a": WirePlayerAction.DISCARD, "tl": [10]}

    def test_draw_available_action_none_tiles_excluded(self):
        """Available action with tiles=None omits the tiles field."""
        event = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                seat=0,
                tile_id=10,
                target="seat_0",
                available_actions=[AvailableActionItem(action="tsumo")],
            ),
            target=SeatTarget(seat=0),
        )
        payload = service_event_payload(event)

        assert payload["aa"][0] == {"a": WirePlayerAction.TSUMO}
        assert "tl" not in payload["aa"][0]


class TestShapeCallPromptPayload:
    """Tests for call prompt wire payload shaping with compact keys."""

    def test_ron_prompt_drops_callers_keeps_caller_seat(self):
        payload = {
            "clt": WireCallType.RON,
            "ti": 42,
            "frs": 1,
            "clr": [0],
        }
        result = shape_call_prompt_payload(payload)

        assert "clr" not in result
        assert result == {
            "clt": WireCallType.RON,
            "ti": 42,
            "frs": 1,
            "cs": 0,
        }

    def test_meld_prompt_replaces_callers_with_available_calls(self):
        payload = {
            "clt": WireCallType.MELD,
            "ti": 42,
            "frs": 1,
            "clr": [
                {"s": 0, "clt": WireMeldCallType.PON, "opt": None},
            ],
        }
        result = shape_call_prompt_payload(payload)

        assert "clr" not in result
        assert result["cs"] == 0
        assert result["ac"] == [{"clt": WireMeldCallType.PON}]

    def test_meld_prompt_preserves_chi_options(self):
        payload = {
            "clt": WireCallType.MELD,
            "ti": 42,
            "frs": 1,
            "clr": [
                {"s": 0, "clt": WireMeldCallType.CHI, "opt": [[40, 44]]},
            ],
        }
        result = shape_call_prompt_payload(payload)

        assert result["cs"] == 0
        assert result["ac"] == [
            {"clt": WireMeldCallType.CHI, "opt": [[40, 44]]},
        ]

    def test_unknown_call_type_returns_payload_unchanged(self):
        payload = {
            "clt": 99,
            "ti": 42,
            "frs": 1,
            "clr": [0],
        }
        result = shape_call_prompt_payload(payload)

        assert result == payload
        assert result["clr"] == [0]

    def test_meld_prompt_multiple_call_types(self):
        payload = {
            "clt": WireCallType.MELD,
            "ti": 55,
            "frs": 3,
            "clr": [
                {"s": 0, "clt": WireMeldCallType.PON, "opt": None},
                {"s": 0, "clt": WireMeldCallType.CHI, "opt": [[57, 63]]},
            ],
        }
        result = shape_call_prompt_payload(payload)

        assert "clr" not in result
        assert result["cs"] == 0
        assert result["ac"] == [
            {"clt": WireMeldCallType.PON},
            {"clt": WireMeldCallType.CHI, "opt": [[57, 63]]},
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

        decoded = decode_meld_compact(payload["m"])
        assert decoded["meld_type"] == "added_kan"
        assert decoded["caller_seat"] == 0
        assert decoded["tile_ids"] == [4, 5, 6, 7]
        assert decoded["called_tile_id"] == 5
        assert decoded["from_seat"] == 2


_HAND_RESULT = HandResultInfo(han=1, fu=30, yaku=[])
_SCORES = {0: 25000, 1: 25000, 2: 25000, 3: 25000}


class TestRoundEndPayload:
    """Tests for round_end flattening with compact keys and exclude_none."""

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
        assert payload["rt"] == WireRoundResultType.TSUMO
        assert "ps" not in payload
        assert "ud" not in payload
        assert payload["ws"] == 0
        assert payload["wt"] == 1

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

        assert payload["ps"] == 2
        assert payload["ud"] == [10]

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

        assert payload["rt"] == WireRoundResultType.DOUBLE_RON
        for winner in payload["wn"]:
            assert "ps" not in winner
            assert "ud" not in winner
