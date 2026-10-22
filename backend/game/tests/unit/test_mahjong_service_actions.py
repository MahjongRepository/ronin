import pytest
from mahjong.tile import TilesConverter

from game.logic.action_result import ActionResult
from game.logic.enums import (
    CallType,
    GameAction,
    GameErrorCode,
    KanType,
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


class TestMahjongGameServiceErrors:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_action__when_game_not_found__should_raise_a_server_fault(self, service):
        with pytest.raises(KeyError):
            service.handle_action(game_id="nonexistent", seat=0, action=GameAction.DISCARD, data={"tile_id": 0})


class TestMahjongGameServiceAddedKanChankan:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_action__when_ai_robber_passes_on_added_kan__should_complete_the_kan_and_draw(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        player = _find_player(service._games["game1"].round_state, "Player")
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
        _update_player(service, game_id="game1", seat=player.seat, tiles=player_hand, melds=(pon,), discards=())
        robber_hand_waits_3p = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        _update_player(service, game_id="game1", seat=robber_seat, tiles=robber_hand_waits_3p, melds=(), discards=())
        _update_round_state(service, "game1", current_player_seat=player.seat, is_after_meld_call=False)

        update = service.handle_action(
            game_id="game1",
            seat=player.seat,
            action=GameAction.CALL_KAN,
            data={"tile_id": pin_3_copies[3], "kan_type": KanType.ADDED},
        )
        assert [(e.event, e.target) for e in update.events] == [
            (EventType.CALL_PROMPT, SeatTarget(seat=robber_seat)),
            (EventType.MELD, BroadcastTarget()),
            (EventType.DRAW, SeatTarget(seat=player.seat)),
            (EventType.FURITEN, SeatTarget(seat=robber_seat)),
        ]
        assert update.events[0].data.call_type == CallType.CHANKAN
        round_state = service._games["game1"].round_state
        assert round_state.pending_call_prompt is None
        assert round_state.players[player.seat].melds[0].meld_type == FrozenMeld.SHOUMINKAN
        assert update.awaiting.kind == WaitKind.TURN
        assert update.awaiting.seats == frozenset({player.seat})


class TestProcessActionResultRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_round_ended__should_return_round_end_event(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        scores = {i: service._games["game1"].round_state.players[i].score for i in range(4)}
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
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED, result=round_end.result)
        result = ActionResult(events=[round_end], state=service._games["game1"], needs_post_discard=True)

        events = service._process_action_result_internal("game1", result)
        assert [e.event for e in events] == [EventType.ROUND_END]
        assert service.is_round_advance_pending("game1")


class TestMahjongGameServiceChankanPrompt:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_chankan_prompt_waits_for_human_player__should_keep_it_open(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        prompt = PendingCallPrompt(
            kind=PromptKind.CHANKAN,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({player.seat}),
            callers=(Caller(seat=player.seat, can_ron=True),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)
        chankan_prompt = CallPromptEvent(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=0,
            callers=[player.seat],
            target=SeatTarget(seat=player.seat),
        )

        result = ActionResult(events=[chankan_prompt], state=service._games["game1"])
        events = service._process_action_result_internal("game1", result)
        assert [e.data for e in events] == [chankan_prompt]
        assert service._games["game1"].round_state.pending_call_prompt == prompt


class TestNoDataActionDispatchRouting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    @pytest.mark.parametrize(
        "action",
        [GameAction.DECLARE_TSUMO, GameAction.CALL_KYUUSHU],
    )
    def test_handle_action__when_no_data_action_out_of_turn__should_answer_error_and_run_nothing(self, service, action):
        service.start_game("game1", ["Player"], seed="a" * 192)
        player = _find_player(service._games["game1"].round_state, "Player")
        ai_seat_on_turn = (player.seat + 1) % 4
        _update_round_state(service, "game1", current_player_seat=ai_seat_on_turn)
        game_state = service.get_game_state("game1")

        update = service.handle_action(game_id="game1", seat=player.seat, action=action, data={})
        assert [(e.event, e.data.code) for e in update.events] == [(EventType.ERROR, GameErrorCode.NOT_YOUR_TURN)]
        assert service.get_game_state("game1") is game_state
        assert update.awaiting.wait_id == game_state.wait_id

    @pytest.mark.parametrize(
        ("action", "data", "code"),
        [
            (GameAction.CALL_RON, {}, GameErrorCode.INVALID_RON),
            (GameAction.CALL_CHI, {"tile_id": 0, "sequence_tiles": (4, 8)}, GameErrorCode.INVALID_CHI),
        ],
    )
    def test_handle_action__when_call_without_call_prompt__should_return_error_event(self, service, action, data, code):
        player_seat = service.start_game("game1", ["Player"], seed="a" * 192).seats[0]

        events = service.handle_action(game_id="game1", seat=player_seat, action=action, data=data).events
        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert events[0].data.code == code
