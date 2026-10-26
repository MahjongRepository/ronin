import pytest

from game.logic.enums import CallType, MeldViewType, WaitKind, WireCallType, WireMeldCallType, WirePlayerAction
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    DrawEvent,
    EventType,
    MeldEvent,
    RoundEndEvent,
    SeatTarget,
    ServiceEvent,
    TurnEvent,
)
from game.logic.service import Awaiting
from game.logic.types import (
    AvailableActionItem,
    DoubleRonResult,
    DoubleRonWinner,
    HandResultInfo,
    TsumoResult,
)
from game.messaging.event_payload import (
    EVENT_TYPE_INT,
    service_event_payload,
    shape_call_prompt_payload,
    stamp_wait_id,
)
from game.wire.compact import decode_discard, decode_draw
from game.wire.enums import WireRoundResultType
from shared.lib.melds import EVENT_TYPE_MELD, decode_meld_compact


class TestEventTypeIntExhaustiveness:
    def test_event_type_int__should_map_every_event_type(self):
        missing = set(EventType) - set(EVENT_TYPE_INT)
        assert not missing, f"EVENT_TYPE_INT missing entries for: {missing}"

    def test_event_type_int__should_have_unique_values(self):
        values = list(EVENT_TYPE_INT.values())
        assert len(values) == len(set(values)), "EVENT_TYPE_INT has duplicate integer values"


class TestServiceEventPayload:
    def test_service_event_payload__when_discard__should_pack_into_integer(self):
        event = ServiceEvent(
            data=DiscardEvent(seat=0, tile_id=10, is_riichi=True),
        )
        payload = service_event_payload(event)
        assert payload["t"] == EVENT_TYPE_INT[EventType.DISCARD]
        assert set(payload.keys()) == {"t", "d"}

        seat, tile_id, is_tsumogiri, is_riichi = decode_discard(payload["d"])
        assert seat == 0
        assert tile_id == 10
        assert is_tsumogiri is False
        assert is_riichi is True

    def test_service_event_payload__when_draw__should_pack_into_integer(self):
        event = ServiceEvent(
            data=DrawEvent(seat=1, tile_id=42, target=SeatTarget(seat=1)),
        )
        payload = service_event_payload(event)
        assert payload["t"] == EVENT_TYPE_INT[EventType.DRAW]
        assert set(payload.keys()) == {"t", "d"}

        seat, tile_id = decode_draw(payload["d"])
        assert seat == 1
        assert tile_id == 42

    def test_service_event_payload__when_draw_has_available_actions__should_include_them(self):
        event = ServiceEvent(
            data=DrawEvent(
                seat=0,
                tile_id=10,
                target=SeatTarget(seat=0),
                available_actions=[AvailableActionItem(action="discard", tiles=[10])],
            ),
        )
        payload = service_event_payload(event)
        assert "aa" in payload
        assert len(payload["aa"]) == 1
        assert payload["aa"][0] == {"a": WirePlayerAction.DISCARD, "tl": [10]}

    def test_service_event_payload__when_available_action_has_no_tiles__should_omit_tile_list(self):
        event = ServiceEvent(
            data=DrawEvent(
                seat=0,
                tile_id=10,
                target=SeatTarget(seat=0),
                available_actions=[AvailableActionItem(action="tsumo")],
            ),
        )
        payload = service_event_payload(event)
        assert payload["aa"][0] == {"a": WirePlayerAction.TSUMO}
        assert "tl" not in payload["aa"][0]

    def test_service_event_payload__when_turn_event__should_carry_only_type_and_kuikae_types(self):
        event = ServiceEvent(data=TurnEvent(kuikae_tiles=[4, 7], target=SeatTarget(seat=0)))

        payload = service_event_payload(event)
        assert payload == {"t": 12, "kt": [4, 7]}


class TestShapeCallPromptPayload:
    def test_shape_call_prompt_payload__when_ron_prompt__should_drop_callers_and_keep_caller_seat(self):
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

    def test_shape_call_prompt_payload__when_ron_prompt_seat_can_also_pon__should_list_the_pon(self):
        payload = {
            "clt": WireCallType.RON,
            "ti": 42,
            "frs": 1,
            "clr": [{"s": 2, "clt": WireMeldCallType.PON, "opt": None}],
        }
        result = shape_call_prompt_payload(payload)
        assert result == {
            "clt": WireCallType.RON,
            "ti": 42,
            "frs": 1,
            "cs": 2,
            "ac": [{"clt": WireMeldCallType.PON}],
        }

    def test_shape_call_prompt_payload__when_meld_prompt_has_multiple_call_types__should_list_all_call_types(self):
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
    def test_meld_event_payload__should_use_compact_format(self):
        event = ServiceEvent(
            data=MeldEvent(
                meld_type=MeldViewType.ADDED_KAN,
                caller_seat=0,
                tile_ids=[4, 5, 6, 7],
                called_tile_id=5,
                from_seat=2,
            ),
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


_HAND_RESULT = HandResultInfo(han=1, fu=30, yaku=[], points=1000)
_SCORES = {0: 25000, 1: 25000, 2: 25000, 3: 25000}


def _meld(meld_type: MeldViewType, caller_seat: int) -> MeldEvent:
    return MeldEvent(meld_type=meld_type, caller_seat=caller_seat, from_seat=0, tile_ids=[8, 9, 10], called_tile_id=8)


def _prompt_to(seat: int) -> CallPromptEvent:
    return CallPromptEvent(
        call_type=CallType.MELD, tile_id=8, from_seat=0, callers=[seat], target=SeatTarget(seat=seat)
    )


def _round_end() -> RoundEndEvent:
    return RoundEndEvent(
        result=TsumoResult(
            winner_seat=0,
            hand_result=_HAND_RESULT,
            scores=_SCORES,
            score_changes=_SCORES,
            riichi_sticks_collected=0,
            closed_tiles=[],
            melds=[],
            win_tile=1,
        )
    )


class TestStampWaitId:
    @pytest.mark.parametrize(
        ("kind", "event", "stamped"),
        [
            (WaitKind.TURN, DrawEvent(seat=1, tile_id=8, target=SeatTarget(seat=1)), True),
            (WaitKind.TURN, DrawEvent(seat=2, tile_id=8, target=SeatTarget(seat=2)), False),
            (WaitKind.TURN, TurnEvent(kuikae_tiles=[], target=SeatTarget(seat=1)), True),
            (WaitKind.TURN, _meld(MeldViewType.PON, caller_seat=1), False),
            (WaitKind.TURN, _meld(MeldViewType.CLOSED_KAN, caller_seat=1), False),
            (WaitKind.CALL, _prompt_to(1), True),
            (WaitKind.CALL, _prompt_to(2), False),
            (WaitKind.ROUND_ADVANCE, _round_end(), True),
            (WaitKind.NONE, _round_end(), False),
        ],
        ids=[
            "turn_draw",
            "other_seats_draw",
            "turn_after_own_call",
            "own_pon_before_its_turn_event",
            "kan_before_its_draw",
            "call_prompt",
            "other_seats_prompt",
            "round_end",
            "round_end_of_the_game",
        ],
    )
    def test_stamp_wait_id__when_event_may_open_the_wait__should_stamp_only_the_opening_one(self, kind, event, stamped):
        awaiting = Awaiting(kind=kind, seats=frozenset({1}), wait_id=7, round_number=0)
        service_event = ServiceEvent(data=event)

        payload = stamp_wait_id(service_event_payload(service_event), service_event, awaiting)
        assert payload.get("wi") == (7 if stamped else None)


class TestRoundEndPayload:
    def test_round_end_payload__when_tsumo_fields_none__should_omit_them(self):
        event = ServiceEvent(
            data=RoundEndEvent(
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
        )
        payload = service_event_payload(event)
        assert "result" not in payload
        assert payload["rt"] == WireRoundResultType.TSUMO
        assert "ps" not in payload
        assert "ud" not in payload
        assert payload["ws"] == 0
        assert payload["wt"] == 1

    def test_round_end_payload__when_tsumo_fields_present__should_keep_them(self):
        event = ServiceEvent(
            data=RoundEndEvent(
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
        )
        payload = service_event_payload(event)
        assert payload["ps"] == 2
        assert payload["ud"] == [10]
        assert payload["hr"]["pt"] == 10

    def test_round_end_payload__when_double_ron_winner_fields_none__should_omit_them(self):
        event = ServiceEvent(
            data=RoundEndEvent(
                result=DoubleRonResult(
                    loser_seat=1,
                    winning_tile=10,
                    winners=[
                        DoubleRonWinner(
                            winner_seat=0,
                            hand_result=_HAND_RESULT,
                            score_changes=_SCORES,
                            riichi_sticks_collected=0,
                            closed_tiles=[],
                            melds=[],
                        ),
                        DoubleRonWinner(
                            winner_seat=2,
                            hand_result=_HAND_RESULT,
                            score_changes=_SCORES,
                            riichi_sticks_collected=0,
                            closed_tiles=[],
                            melds=[],
                        ),
                    ],
                    scores=_SCORES,
                    score_changes=_SCORES,
                ),
            ),
        )
        payload = service_event_payload(event)
        assert payload["rt"] == WireRoundResultType.DOUBLE_RON
        for winner in payload["wn"]:
            assert "ps" not in winner
            assert "ud" not in winner
