import pytest

from game.logic.enums import (
    CallType,
    GameEndCause,
    HandLimit,
    KanType,
    MeldViewType,
    PaoShare,
    WaitKind,
    WireCallType,
    WireMeldCallType,
    WirePlayerAction,
)
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    DrawEvent,
    EventType,
    GameEndedEvent,
    MeldEvent,
    RoundEndEvent,
    SeatTarget,
    TurnEvent,
)
from game.logic.service import Awaiting
from game.logic.types import (
    AvailableActionItem,
    DoubleRonResult,
    DoubleRonWinner,
    HandResultInfo,
    PaoLiability,
    PlayerStanding,
    TsumoResult,
    YakuInfo,
)
from game.messaging.event_payload import (
    EVENT_TYPE_INT,
    game_event_payload,
    shape_call_prompt_payload,
    stamp_wait_id,
)
from game.wire.compact import decode_discard, decode_draw
from game.wire.enums import WireRoundResultType
from game.wire.keys import WireKey
from shared.lib.melds import EVENT_TYPE_MELD, decode_meld_compact


class TestEventTypeIntExhaustiveness:
    def test_event_type_int__should_map_every_event_type(self):
        missing = set(EventType) - set(EVENT_TYPE_INT)
        assert not missing, f"EVENT_TYPE_INT missing entries for: {missing}"

    def test_event_type_int__should_have_unique_values(self):
        values = list(EVENT_TYPE_INT.values())
        assert len(values) == len(set(values)), "EVENT_TYPE_INT has duplicate integer values"


class TestGameEventPayload:
    def test_game_event_payload__when_discard__should_pack_into_integer(self):
        event = DiscardEvent(seat=0, tile_id=10, is_riichi=True)
        payload = game_event_payload(event)
        assert payload[WireKey.EVENT_TYPE] == EVENT_TYPE_INT[EventType.DISCARD]
        assert set(payload.keys()) == {WireKey.EVENT_TYPE, WireKey.PACKED_MOVE}

        seat, tile_id, is_tsumogiri, is_riichi = decode_discard(payload[WireKey.PACKED_MOVE])
        assert seat == 0
        assert tile_id == 10
        assert is_tsumogiri is False
        assert is_riichi is True

    def test_game_event_payload__when_game_ends_with_sticks_unawarded__should_send_their_count_bonus_and_cause(
        self,
    ):
        standings = [PlayerStanding(seat=seat, score=25000, final_score=0) for seat in range(4)]
        event = GameEndedEvent(
            winner_seat=0,
            standings=standings,
            leftover_riichi_bonus=0,
            leftover_riichi_sticks=2,
            num_rounds=8,
            end_cause=GameEndCause.EXTENSION_LIMIT,
        )

        payload = game_event_payload(event)

        assert payload[WireKey.EVENT_TYPE] == EVENT_TYPE_INT[EventType.GAME_END]
        assert (
            payload[WireKey.LEFTOVER_BONUS],
            payload[WireKey.LEFTOVER_RIICHI],
            payload[WireKey.ROUND_COUNT],
            payload[WireKey.END_CAUSE],
        ) == (0, 2, 8, "extension_limit")

    def test_game_event_payload__when_draw__should_pack_into_integer_beside_the_live_wall_left(self):
        event = DrawEvent(seat=1, tile_id=42, tiles_remaining=69, target=SeatTarget(seat=1))
        payload = game_event_payload(event)
        assert payload[WireKey.EVENT_TYPE] == EVENT_TYPE_INT[EventType.DRAW]
        assert set(payload.keys()) == {WireKey.EVENT_TYPE, WireKey.PACKED_MOVE, WireKey.TILES_REMAINING}
        assert payload[WireKey.TILES_REMAINING] == 69

        seat, tile_id = decode_draw(payload[WireKey.PACKED_MOVE])
        assert seat == 1
        assert tile_id == 42

    def test_game_event_payload__when_draw_has_available_actions__should_include_them(self):
        event = DrawEvent(
            seat=0,
            tile_id=10,
            tiles_remaining=69,
            target=SeatTarget(seat=0),
            available_actions=[AvailableActionItem(action="discard", tiles=[10])],
        )
        payload = game_event_payload(event)
        assert WireKey.AVAILABLE_ACTIONS in payload
        assert len(payload[WireKey.AVAILABLE_ACTIONS]) == 1
        assert payload[WireKey.AVAILABLE_ACTIONS][0] == {WireKey.ACTION: WirePlayerAction.DISCARD, WireKey.TILES: [10]}

    def test_game_event_payload__when_available_action_has_no_tiles__should_omit_tile_list(self):
        event = DrawEvent(
            seat=0,
            tile_id=10,
            tiles_remaining=69,
            target=SeatTarget(seat=0),
            available_actions=[AvailableActionItem(action="tsumo")],
        )
        payload = game_event_payload(event)
        assert payload[WireKey.AVAILABLE_ACTIONS][0] == {WireKey.ACTION: WirePlayerAction.TSUMO}
        assert WireKey.TILES not in payload[WireKey.AVAILABLE_ACTIONS][0]

    def test_game_event_payload__when_chankan_prompt__should_name_the_kan_it_offers_to_rob(self):
        chankan = CallPromptEvent(
            call_type=CallType.CHANKAN,
            tile_id=8,
            from_seat=0,
            callers=[1],
            kan_type=KanType.CLOSED,
            target=SeatTarget(seat=1),
        )

        assert game_event_payload(chankan)[WireKey.KAN_TYPE] == "closed"
        assert WireKey.KAN_TYPE not in game_event_payload(_prompt_to(1))

    def test_game_event_payload__when_turn_event__should_carry_only_type_and_kuikae_types(self):
        event = TurnEvent(kuikae_tiles=[4, 7], target=SeatTarget(seat=0))

        payload = game_event_payload(event)
        assert payload == {WireKey.EVENT_TYPE: 12, WireKey.KUIKAE_TILES: [4, 7]}


class TestShapeCallPromptPayload:
    def test_shape_call_prompt_payload__when_ron_prompt__should_drop_callers_and_keep_caller_seat(self):
        payload = {
            WireKey.CALL_TYPE: WireCallType.RON,
            WireKey.TILE_ID: 42,
            WireKey.FROM_SEAT: 1,
            WireKey.CALLERS: [0],
        }
        result = shape_call_prompt_payload(payload)
        assert WireKey.CALLERS not in result
        assert result == {
            WireKey.CALL_TYPE: WireCallType.RON,
            WireKey.TILE_ID: 42,
            WireKey.FROM_SEAT: 1,
            WireKey.CALLER_SEAT: 0,
        }

    def test_shape_call_prompt_payload__when_ron_prompt_seat_can_also_pon__should_list_the_pon(self):
        payload = {
            WireKey.CALL_TYPE: WireCallType.RON,
            WireKey.TILE_ID: 42,
            WireKey.FROM_SEAT: 1,
            WireKey.CALLERS: [{WireKey.SEAT: 2, WireKey.CALL_TYPE: WireMeldCallType.PON, WireKey.CALL_OPTIONS: None}],
        }
        result = shape_call_prompt_payload(payload)
        assert result == {
            WireKey.CALL_TYPE: WireCallType.RON,
            WireKey.TILE_ID: 42,
            WireKey.FROM_SEAT: 1,
            WireKey.CALLER_SEAT: 2,
            WireKey.AVAILABLE_CALLS: [{WireKey.CALL_TYPE: WireMeldCallType.PON}],
        }

    def test_shape_call_prompt_payload__when_meld_prompt_has_multiple_call_types__should_list_all_call_types(self):
        payload = {
            WireKey.CALL_TYPE: WireCallType.MELD,
            WireKey.TILE_ID: 55,
            WireKey.FROM_SEAT: 3,
            WireKey.CALLERS: [
                {WireKey.SEAT: 0, WireKey.CALL_TYPE: WireMeldCallType.PON, WireKey.CALL_OPTIONS: None},
                {WireKey.SEAT: 0, WireKey.CALL_TYPE: WireMeldCallType.CHI, WireKey.CALL_OPTIONS: [[57, 63]]},
            ],
        }
        result = shape_call_prompt_payload(payload)
        assert WireKey.CALLERS not in result
        assert result[WireKey.CALLER_SEAT] == 0
        assert result[WireKey.AVAILABLE_CALLS] == [
            {WireKey.CALL_TYPE: WireMeldCallType.PON},
            {WireKey.CALL_TYPE: WireMeldCallType.CHI, WireKey.CALL_OPTIONS: [[57, 63]]},
        ]


class TestMeldEventPayload:
    def test_meld_event_payload__should_use_compact_format(self):
        event = MeldEvent(
            meld_type=MeldViewType.ADDED_KAN,
            caller_seat=0,
            tile_ids=[4, 5, 6, 7],
            called_tile_id=5,
            from_seat=2,
            added_tile_id=6,
        )
        payload = game_event_payload(event)
        assert payload[WireKey.EVENT_TYPE] == EVENT_TYPE_MELD
        assert WireKey.PACKED_MELD in payload
        assert set(payload.keys()) == {WireKey.EVENT_TYPE, WireKey.PACKED_MELD}

        decoded = decode_meld_compact(payload[WireKey.PACKED_MELD])
        assert decoded["meld_type"] == "added_kan"
        assert decoded["caller_seat"] == 0
        assert decoded["tile_ids"] == [4, 5, 6, 7]
        assert decoded["called_tile_id"] == 5
        assert decoded["added_tile_id"] == 6
        assert decoded["from_seat"] == 2


_HAND_RESULT = HandResultInfo(limit=HandLimit.NONE, han=1, fu=30, yaku=[], points=1000)
_SCORES = {0: 25000, 1: 25000, 2: 25000, 3: 25000}


def _meld(meld_type: MeldViewType, caller_seat: int) -> MeldEvent:
    return MeldEvent(meld_type=meld_type, caller_seat=caller_seat, from_seat=0, tile_ids=[8, 9, 10], called_tile_id=8)


def _prompt_to(seat: int) -> CallPromptEvent:
    return CallPromptEvent(
        call_type=CallType.MELD, tile_id=8, from_seat=0, callers=[seat], target=SeatTarget(seat=seat)
    )


def _round_end() -> RoundEndEvent:
    return RoundEndEvent(
        dealer_seat=0,
        dora_indicators=[],
        riichi_sticks=0,
        result=TsumoResult(
            honba_bonus=0,
            winner_seat=0,
            hand_result=_HAND_RESULT,
            scores=_SCORES,
            score_changes=_SCORES,
            riichi_sticks_collected=0,
            closed_tiles=[],
            melds=[],
            win_tile=1,
        ),
    )


class TestStampWaitId:
    @pytest.mark.parametrize(
        ("kind", "event", "stamped"),
        [
            (WaitKind.TURN, DrawEvent(seat=1, tile_id=8, tiles_remaining=69, target=SeatTarget(seat=1)), True),
            (WaitKind.TURN, DrawEvent(seat=2, tile_id=8, tiles_remaining=69, target=SeatTarget(seat=2)), False),
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

        payload = stamp_wait_id(game_event_payload(event), event=event, awaiting=awaiting, wait_id=3)
        assert payload.get(WireKey.WAIT_ID) == (3 if stamped else None)


class TestRoundEndPayload:
    def test_round_end_payload__when_tsumo_fields_none__should_omit_them(self):
        event = RoundEndEvent(
            dealer_seat=0,
            dora_indicators=[],
            riichi_sticks=0,
            result=TsumoResult(
                honba_bonus=0,
                winner_seat=0,
                hand_result=_HAND_RESULT,
                scores=_SCORES,
                score_changes=_SCORES,
                riichi_sticks_collected=0,
                closed_tiles=[],
                melds=[],
                win_tile=1,
            ),
        )
        payload = game_event_payload(event)
        assert "result" not in payload
        assert (payload[WireKey.RESULT_TYPE], payload[WireKey.RIICHI_STICKS]) == (WireRoundResultType.TSUMO, 0)
        assert WireKey.PAO_SEAT not in payload
        assert WireKey.URA_DORA not in payload
        assert payload[WireKey.WINNER_SEAT] == 0
        assert payload[WireKey.WINNING_TILE] == 1

    def test_round_end_payload__when_tsumo_fields_present__should_keep_them(self):
        yakuman_hand = HandResultInfo(
            han=13,
            fu=30,
            yaku=[YakuInfo(yaku_id=103, han=13, yakuman_count=1)],
            points=32000,
            limit=HandLimit.YAKUMAN,
            yakuman_count=1,
        )
        event = RoundEndEvent(
            dealer_seat=3,
            dora_indicators=[5, 9],
            riichi_sticks=0,
            result=TsumoResult(
                honba_bonus=600,
                winner_seat=0,
                hand_result=yakuman_hand,
                scores=_SCORES,
                score_changes=_SCORES,
                riichi_sticks_collected=0,
                closed_tiles=[],
                melds=[],
                win_tile=1,
                pao_seat=2,
                pao=PaoLiability(yaku_ids=[103], share=PaoShare.ALL, pays_honba=True),
                ura_dora_indicators=[10],
            ),
        )
        payload = game_event_payload(event)
        assert (payload[WireKey.DEALER], payload[WireKey.DORA_INDICATORS]) == (3, [5, 9])
        assert (payload[WireKey.PAO_SEAT], payload[WireKey.PAO_LIABILITY]) == (
            2,
            {WireKey.YAKU: [103], WireKey.PAO_SHARE: "all", WireKey.PAYS_HONBA: True},
        )
        assert (payload[WireKey.HONBA_BONUS], payload[WireKey.URA_DORA]) == (6, [10])
        assert payload[WireKey.HAND_RESULT] == {
            WireKey.HAN: 13,
            WireKey.FU: 30,
            WireKey.YAKU: [{WireKey.YAKU_ID: 103, WireKey.HAN: 13, WireKey.YAKU_YAKUMAN_COUNT: 1}],
            WireKey.POINTS: 320,
            WireKey.HAND_LIMIT: "yakuman",
            WireKey.YAKUMAN_COUNT: 1,
        }

    def test_round_end_payload__when_double_ron_winner_fields_none__should_omit_them(self):
        event = RoundEndEvent(
            dealer_seat=0,
            dora_indicators=[],
            riichi_sticks=0,
            result=DoubleRonResult(
                loser_seat=1,
                winning_tile=10,
                winners=[
                    DoubleRonWinner(
                        honba_bonus=0,
                        winner_seat=0,
                        hand_result=_HAND_RESULT,
                        score_changes=_SCORES,
                        riichi_sticks_collected=0,
                        closed_tiles=[],
                        melds=[],
                    ),
                    DoubleRonWinner(
                        honba_bonus=0,
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
        )
        payload = game_event_payload(event)
        assert payload[WireKey.RESULT_TYPE] == WireRoundResultType.DOUBLE_RON
        for winner in payload[WireKey.WINNERS]:
            assert WireKey.PAO_SEAT not in winner
            assert WireKey.URA_DORA not in winner
