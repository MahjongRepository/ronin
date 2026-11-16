import pytest
from mahjong.tile import TilesConverter

from game.logic.action_result import ActionResult
from game.logic.decision import Chi, Kan, Kyuushu, Pon, Ron, Tsumo
from game.logic.enums import (
    KanType,
    MeldViewType,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import (
    BroadcastTarget,
    EventType,
    RoundEndEvent,
    SeatTarget,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.refusal import Refusal, RefusalCode, RefusalKind
from game.logic.service import Call, RoundOver, Turn
from game.logic.types import ExhaustiveDrawResult
from game.tests.helpers.builders import answer_with_defaults, start_game_in_play
from game.tests.unit.logic.helpers import (
    _first_human,
    _update_player,
    _update_round_state,
)


class TestMahjongGameServiceAddedKanChankan:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_act__when_the_robber_passes_on_an_added_kan__should_complete_the_kan_and_draw(self, service):
        runtime = start_game_in_play(service, humans=1, seed="a" * 192).runtime
        player = _first_human(runtime.state)
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

        assert service.act(runtime, player.seat, Kan(kan_type=KanType.ADDED, tile=pin_3_copies[3])) == []
        assert service.get_awaiting(runtime) == Call(seats=frozenset({robber_seat}))

        events = answer_with_defaults(service, runtime, seats=frozenset({robber_seat}))
        others = [seat for seat in range(4) if seat != player.seat]
        assert [(e.type, e.target) for e in events] == [
            (EventType.MELD, BroadcastTarget()),
            (EventType.DRAW, SeatTarget(seat=player.seat)),
            *((EventType.DRAW_NOTICE, SeatTarget(seat=seat)) for seat in others),
            (EventType.FURITEN, SeatTarget(seat=robber_seat)),
        ]
        added_kan = events[0]
        assert (added_kan.meld_type, added_kan.called_tile_id, added_kan.from_seat) == (
            MeldViewType.ADDED_KAN,
            pin_3_copies[0],
            (player.seat + 3) % 4,
        )
        round_state = runtime.state.round_state
        assert round_state.pending_call_prompt is None
        assert round_state.players[player.seat].melds[0].meld_type == FrozenMeld.SHOUMINKAN
        assert service.get_awaiting(runtime) == Turn(seat=player.seat)


class TestProcessActionResultRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_round_ended__should_return_round_end_event(self, service):
        runtime = start_game_in_play(service, humans=1, seed="a" * 192).runtime

        scores = {i: runtime.state.round_state.players[i].score for i in range(4)}
        round_end = RoundEndEvent(
            dealer_seat=0,
            dora_indicators=[],
            riichi_sticks=0,
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

        events = service._commit_and_process(runtime, result)
        assert [e.type for e in events] == [EventType.ROUND_END]
        assert service.get_awaiting(runtime) == RoundOver()


class TestNoDataActionDispatchRouting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    @pytest.mark.parametrize(
        "action",
        [Tsumo(), Kyuushu()],
    )
    def test_act__when_no_data_action_out_of_turn__should_refuse_it_and_run_nothing(self, service, action):
        runtime = start_game_in_play(service, humans=1, seed="a" * 192).runtime
        player = _first_human(runtime.state)
        ai_seat_on_turn = (player.seat + 1) % 4
        _update_round_state(runtime, current_player_seat=ai_seat_on_turn)
        game_state = runtime.state

        refusal = service.act(runtime, player.seat, action)
        assert refusal == Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.SEAT_NOT_AWAITED)
        assert runtime.state is game_state

    @pytest.mark.parametrize("action", [Ron(), Pon(), Chi(tiles=(4, 8))])
    def test_act__when_call_without_call_prompt__should_refuse_as_not_awaited(self, service, action):
        start = start_game_in_play(service, humans=1, seed="a" * 192)
        runtime = start.runtime
        player_seat = start.human_seats[0]

        refusal = service.act(runtime, player_seat, action)
        assert refusal == Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.SEAT_NOT_AWAITED)
