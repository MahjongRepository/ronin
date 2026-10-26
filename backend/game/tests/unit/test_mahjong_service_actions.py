import pytest
from mahjong.tile import TilesConverter

from game.logic.action_result import ActionResult
from game.logic.enums import (
    CallType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldViewType,
    PromptKind,
    RoundPhase,
    RoundResultType,
    WaitKind,
)
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    EventType,
    RoundEndEvent,
    SeatTarget,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import Caller, PendingCallPrompt
from game.logic.types import ExhaustiveDrawResult
from game.tests.unit.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)


class TestMahjongGameServiceAddedKanChankan:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_action__when_ai_robber_passes_on_added_kan__should_complete_the_kan_and_draw(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        player = _find_player(runtime.state.round_state, "Player")
        robber_seat = (player.seat + 1) % 4
        pin_3_copies = TilesConverter.string_to_136_array(pin="3333")
        pon = FrozenMeld(
            tiles=tuple(pin_3_copies[:3]),
            meld_type=FrozenMeld.PON,
            opened=True,
            called_tile=pin_3_copies[0],
            who=player.seat,
            from_who=(player.seat + 3) % 4,
        )
        player_hand = (*TilesConverter.string_to_136_array(sou="123456789", honors="1"), pin_3_copies[3])
        _update_player(runtime, seat=player.seat, tiles=player_hand, melds=(pon,), discards=())
        robber_hand_waits_3p = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        _update_player(runtime, seat=robber_seat, tiles=robber_hand_waits_3p, melds=(), discards=())
        _update_round_state(runtime, current_player_seat=player.seat, is_after_meld_call=False)

        update = service.handle_action(
            runtime,
            seat=player.seat,
            action=GameAction.CALL_KAN,
            data={"tile_id": pin_3_copies[3], "kan_type": KanType.ADDED},
        )
        assert [(e.type, e.target) for e in update.events] == [
            (EventType.CALL_PROMPT, SeatTarget(seat=robber_seat)),
            (EventType.MELD, BroadcastTarget()),
            (EventType.DRAW, SeatTarget(seat=player.seat)),
            (EventType.FURITEN, SeatTarget(seat=robber_seat)),
        ]
        assert update.events[0].call_type == CallType.CHANKAN
        added_kan = update.events[1]
        assert (added_kan.meld_type, added_kan.called_tile_id, added_kan.from_seat) == (
            MeldViewType.ADDED_KAN,
            pin_3_copies[0],
            (player.seat + 3) % 4,
        )
        round_state = runtime.state.round_state
        assert round_state.pending_call_prompt is None
        assert round_state.players[player.seat].melds[0].meld_type == FrozenMeld.SHOUMINKAN
        assert update.awaiting.kind == WaitKind.TURN
        assert update.awaiting.seats == frozenset({player.seat})


class TestProcessActionResultRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_round_ended__should_return_round_end_event(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime

        scores = {i: runtime.state.round_state.players[i].score for i in range(4)}
        round_end = RoundEndEvent(
            result=ExhaustiveDrawResult(
                type=RoundResultType.EXHAUSTIVE_DRAW,
                tempai_seats=[],
                noten_seats=[0, 1, 2, 3],
                tenpai_hands=[],
                scores=scores,
                score_changes={},
            ),
        )
        _update_round_state(runtime, phase=RoundPhase.FINISHED, result=round_end.result)
        result = ActionResult(events=[round_end], state=runtime.state)

        events = service._process_action_result_internal(runtime, result)
        assert [e.type for e in events] == [EventType.ROUND_END]
        assert runtime.pending_confirm is not None


class TestMahjongGameServiceChankanPrompt:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_chankan_prompt_waits_for_human_player__should_keep_it_open(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")

        prompt = PendingCallPrompt(
            kind=PromptKind.CHANKAN,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({player.seat}),
            callers=(Caller(seat=player.seat, can_ron=True),),
        )
        _update_round_state(runtime, pending_call_prompt=prompt)
        chankan_prompt = CallPromptEvent(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=0,
            callers=[player.seat],
            target=SeatTarget(seat=player.seat),
        )

        result = ActionResult(events=[chankan_prompt], state=runtime.state)
        events = service._process_action_result_internal(runtime, result)
        assert events == [chankan_prompt]
        assert runtime.state.round_state.pending_call_prompt == prompt


class TestNoDataActionDispatchRouting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    @pytest.mark.parametrize(
        "action",
        [GameAction.DECLARE_TSUMO, GameAction.CALL_KYUUSHU],
    )
    def test_handle_action__when_no_data_action_out_of_turn__should_answer_error_and_run_nothing(self, service, action):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        player = _find_player(runtime.state.round_state, "Player")
        ai_seat_on_turn = (player.seat + 1) % 4
        _update_round_state(runtime, current_player_seat=ai_seat_on_turn)
        game_state = runtime.state

        update = service.handle_action(runtime, seat=player.seat, action=action, data={})
        assert [(e.type, e.code) for e in update.events] == [(EventType.ERROR, GameErrorCode.NOT_YOUR_TURN)]
        assert runtime.state is game_state
        assert update.awaiting.wait_id == game_state.wait_id

    @pytest.mark.parametrize(
        ("action", "data", "code"),
        [
            (GameAction.CALL_RON, {}, GameErrorCode.INVALID_RON),
            (GameAction.CALL_CHI, {"tile_id": 0, "sequence_tiles": (4, 8)}, GameErrorCode.INVALID_CHI),
        ],
    )
    def test_handle_action__when_call_without_call_prompt__should_return_error_event(self, service, action, data, code):
        start = service.start_game("game1", ["Player"], seed="a" * 192)
        runtime = start.runtime
        player_seat = start.seats[0]

        events = service.handle_action(runtime, seat=player_seat, action=action, data=data).events
        assert len(events) == 1
        assert events[0].type == EventType.ERROR
        assert events[0].code == code
