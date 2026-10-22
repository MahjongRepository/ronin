from unittest.mock import patch

import pytest

from game.logic.action_result import ActionResult
from game.logic.enums import CallType, GameAction, GameErrorCode, RoundPhase, RoundResultType
from game.logic.events import (
    CallPromptEvent,
    ErrorEvent,
    EventType,
    RoundEndEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import PendingCallPrompt
from game.logic.types import ExhaustiveDrawResult
from game.tests.unit.helpers import (
    _find_player,
    _update_round_state,
)


class TestMahjongGameServiceErrors:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_action__when_game_not_found__should_return_error_event(self, service):
        events = service.handle_action(
            game_id="nonexistent", player_name="Player", action=GameAction.DISCARD, data={"tile_id": 0}
        )
        assert any(e.event == EventType.ERROR for e in events)
        error_event = next(e for e in events if e.event == EventType.ERROR)
        assert isinstance(error_event.data, ErrorEvent)
        assert "not found" in error_event.data.message

    def test_handle_action__when_player_not_in_game__should_return_error_event(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        events = service.handle_action(
            game_id="game1", player_name="Unknown", action=GameAction.DISCARD, data={"tile_id": 0}
        )
        assert any(e.event == EventType.ERROR for e in events)
        error_event = next(e for e in events if e.event == EventType.ERROR)
        assert isinstance(error_event.data, ErrorEvent)
        assert "not in game" in error_event.data.message


class TestMahjongGameServiceProcessActionResult:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_chankan_prompt_for_ai_player__should_return_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=player.seat,
            pending_seats=frozenset({ai_player_seats[0]}),
            callers=(ai_player_seats[0],),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        chankan_prompt = CallPromptEvent(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=player.seat,
            callers=[ai_player_seats[0]],
            target="all",
        )
        result = ActionResult(
            events=[chankan_prompt],
            needs_post_discard=False,
        )

        cleared_round = game_state.round_state.model_copy(update={"pending_call_prompt": None})
        with patch(
            "game.logic.call_resolution.complete_closed_kan_after_chankan_decline",
            return_value=(cleared_round, game_state, []),
        ):
            events = service._process_action_result_internal("game1", result)

        assert [e.event for e in events] == [EventType.CALL_PROMPT]


class TestProcessActionResultRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_round_ended__should_return_round_end_event(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        scores = {i: service._games["game1"].round_state.players[i].score for i in range(4)}
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        round_end = RoundEndEvent(
            result=ExhaustiveDrawResult(
                type=RoundResultType.EXHAUSTIVE_DRAW,
                tempai_seats=[],
                noten_seats=[0, 1, 2, 3],
                tenpai_hands=[],
                scores=scores,
                score_changes={},
            ),
            target="all",
        )
        result = ActionResult(events=[round_end], needs_post_discard=False)

        events = service._process_action_result_internal("game1", result)
        round_end_events = [e for e in events if e.event == EventType.ROUND_END]
        assert len(round_end_events) == 1


class TestMahjongGameServiceHandleChankanPrompt:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_chankan_prompt__when_caller_is_human_player__should_return_events_unchanged(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({player.seat}),
            callers=(player.seat,),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=0,
                callers=[player.seat],
                target="all",
            ),
            target=SeatTarget(seat=player.seat),
        )
        events = [chankan_prompt]

        result = service._handle_chankan_prompt("game1", events)
        assert result == events

    def test_handle_chankan_prompt__when_caller_is_ai_player__should_process_its_response(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=ai_player_seats[0],
            pending_seats=frozenset({ai_player_seats[1]}),
            callers=(ai_player_seats[1],),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=ai_player_seats[0],
                callers=[ai_player_seats[1]],
                target="all",
            ),
            target=SeatTarget(seat=ai_player_seats[1]),
        )
        events = [chankan_prompt]

        cleared_round = game_state.round_state.model_copy(update={"pending_call_prompt": None})
        with patch(
            "game.logic.call_resolution.complete_closed_kan_after_chankan_decline",
            return_value=(cleared_round, game_state, []),
        ):
            result = service._handle_chankan_prompt("game1", events)

        assert [e.event for e in result] == [EventType.CALL_PROMPT]

    def test_handle_chankan_prompt__when_no_pending_prompt__should_return_events_unchanged(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=0,
                callers=[1],
                target="all",
            ),
            target=SeatTarget(seat=1),
        )
        events = [chankan_prompt]

        result = service._handle_chankan_prompt("game1", events)
        assert result == events


class TestNoDataActionDispatchRouting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    @pytest.mark.parametrize(
        "action",
        [GameAction.DECLARE_TSUMO, GameAction.CALL_KYUUSHU],
    )
    def test_handle_action__when_no_data_action_out_of_turn__should_return_error_event(self, service, action):
        service.start_game("game1", ["Player"], seed="a" * 192)
        player = _find_player(service._games["game1"].round_state, "Player")
        other_seat = (player.seat + 1) % 4
        _update_round_state(service, "game1", current_player_seat=other_seat)

        events = service.handle_action(game_id="game1", player_name="Player", action=action, data={})
        assert events[0].event == EventType.ERROR
        assert events[0].data.code == GameErrorCode.NOT_YOUR_TURN

    @pytest.mark.parametrize(
        ("action", "data", "code"),
        [
            (GameAction.CALL_RON, {}, GameErrorCode.INVALID_RON),
            (GameAction.CALL_CHI, {"tile_id": 0, "sequence_tiles": (4, 8)}, GameErrorCode.INVALID_CHI),
        ],
    )
    def test_handle_action__when_call_without_call_prompt__should_return_error_event(self, service, action, data, code):
        service.start_game("game1", ["Player"], seed="a" * 192)

        events = service.handle_action(game_id="game1", player_name="Player", action=action, data=data)
        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert events[0].data.code == code


class TestChankanPromptResolvedPath:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_chankan_prompt__when_ai_responses_resolve_prompt__should_check_round_end(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=ai_player_seats[0],
            pending_seats=frozenset({ai_player_seats[1]}),
            callers=(ai_player_seats[1],),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        def mock_dispatch_clearing_prompt(_game_id, _prompt, _evts):
            _update_round_state(service, "game1", pending_call_prompt=None)

        events: list[ServiceEvent] = []
        with (
            patch.object(
                service,
                "_dispatch_ai_player_call_responses",
                side_effect=mock_dispatch_clearing_prompt,
            ),
            patch.object(service, "_check_and_handle_round_end") as mock_round_end,
        ):
            result = service._handle_chankan_prompt("game1", events)

        assert isinstance(result, list)
        mock_round_end.assert_called_once_with("game1", events)
