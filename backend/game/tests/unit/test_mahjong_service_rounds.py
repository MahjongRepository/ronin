from unittest.mock import patch

import pytest

from game.logic.action_result import ActionResult
from game.logic.enums import CallType, GameAction, MeldCallType, PromptKind, RoundPhase, TimeoutType, WaitKind
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    ErrorEvent,
    EventType,
    GameEvent,
    RoundEndEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.exceptions import GeneratedActionError
from game.logic.mahjong_service import MahjongGameService
from game.logic.service import Awaiting
from game.logic.state import Caller, MeldOption, PendingCallPrompt
from game.logic.tiles import tile_to_34
from game.logic.types import (
    ExhaustiveDrawResult,
    MeldCaller,
    TenpaiHand,
)
from game.logic.wall import Wall
from game.tests.unit.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)


def _post_discard_result(service: MahjongGameService, events: list[GameEvent]) -> ActionResult:
    return ActionResult(events, state=service._games["game1"], needs_post_discard=True)


class TestMahjongGameServiceHandleTimeout:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_timeout__when_meld_timeout_without_pending_prompt__should_return_no_events(self, service):
        player_seat = service.start_game("game1", ["Player"], seed="a" * 192).seats[0]

        events = service.handle_timeout(game_id="game1", seat=player_seat, timeout_type=TimeoutType.MELD).events
        assert events == []

    def test_handle_timeout__when_meld_timeout_with_pending_prompt__should_pass_for_the_seat(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        round_state = game_state.round_state
        player = _find_player(round_state, "Player")

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=(player.seat + 1) % 4,
            pending_seats=frozenset({player.seat}),
            callers=(Caller(seat=player.seat, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.MELD).events
        assert not any(isinstance(e.data, ErrorEvent) for e in events)
        assert service._games["game1"].round_state.pending_call_prompt != prompt

    def test_handle_timeout__when_turn_timeout_and_prompt_pending_for_others__should_return_no_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        round_state = game_state.round_state
        player = _find_player(round_state, "Player")

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=(player.seat + 1) % 4,
            pending_seats=frozenset({(player.seat + 2) % 4}),
            callers=(Caller(seat=(player.seat + 2) % 4, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.TURN).events
        assert events == []


class TestMahjongGameServiceCheckAndHandleRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_check_and_handle_round_end__when_round_finished__should_handle_it_once(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        round_result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED, result=round_result)
        events = [
            ServiceEvent(
                data=RoundEndEvent(result=round_result),
            ),
        ]

        result = service._check_and_handle_round_end("game1", events)
        assert result is True
        assert [e.event for e in events] == [EventType.ROUND_END]
        assert service.is_round_advance_pending("game1")

        with pytest.raises(AssertionError, match="round end already handled"):
            service._check_and_handle_round_end("game1", [])


class TestMahjongGameServiceAfterDiscard:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_discard_prompt_waits_for_human_player__should_return_its_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({player.seat}),
            callers=(Caller(seat=player.seat, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        prompt_event = CallPromptEvent(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            callers=[player.seat],
            target=SeatTarget(seat=player.seat),
        )

        result = service._process_action_result_internal("game1", _post_discard_result(service, [prompt_event]))
        assert [(e.event, e.target) for e in result] == [(EventType.CALL_PROMPT, SeatTarget(seat=player.seat))]

    def test_process_action_result__when_discard_prompt_waits_only_for_ai_player__should_answer_it_and_draw(
        self, service
    ):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        round_state = game_state.round_state

        current_seat = round_state.current_player_seat
        current_player = round_state.players[current_seat]
        if len(current_player.tiles) > 13:
            _update_player(service, game_id="game1", seat=current_seat, tiles=tuple(list(current_player.tiles)[:13]))
            round_state = service._games["game1"].round_state

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)
        ai_player_seat = ai_player_seats[0]
        ai_player_tile = (
            round_state.players[ai_player_seat].tiles[0] if round_state.players[ai_player_seat].tiles else 0
        )

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=ai_player_tile,
            from_seat=0,
            pending_seats=frozenset({ai_player_seat}),
            callers=(Caller(seat=ai_player_seat, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        prompt_event = CallPromptEvent(
            call_type=CallType.MELD,
            tile_id=ai_player_tile,
            from_seat=0,
            callers=[MeldCaller(seat=ai_player_seat, call_type=MeldCallType.PON)],
            target=SeatTarget(seat=ai_player_seat),
        )

        result = service._process_action_result_internal("game1", _post_discard_result(service, [prompt_event]))
        assert [e.event for e in result] == [EventType.CALL_PROMPT, EventType.DRAW]

    def test_process_action_result__when_discard_has_no_callers__should_draw_for_next_player(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        round_state = game_state.round_state

        current_seat = round_state.current_player_seat
        current_player = round_state.players[current_seat]
        if len(current_player.tiles) > 13:
            _update_player(service, game_id="game1", seat=current_seat, tiles=tuple(list(current_player.tiles)[:13]))

        result = service._process_action_result_internal("game1", _post_discard_result(service, []))
        assert [(e.event, e.target) for e in result] == [(EventType.DRAW, SeatTarget(seat=current_seat))]


class TestMahjongGameServiceTimeoutIntegration:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_timeout__when_turn_timeout_on_players_turn__should_discard_tile(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        player_tiles = list(player.tiles)
        live_tiles = list(game_state.round_state.wall.live_tiles)
        if len(player_tiles) == 13 and live_tiles:
            player_tiles.append(live_tiles.pop(0))

        _update_player(service, game_id="game1", seat=player.seat, tiles=tuple(player_tiles))
        new_wall = game_state.round_state.wall.model_copy(update={"live_tiles": tuple(live_tiles)})
        _update_round_state(service, "game1", current_player_seat=player.seat, wall=new_wall)

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.TURN).events
        assert events[0].data == DiscardEvent(seat=player.seat, tile_id=player_tiles[-1], is_tsumogiri=True)

    def test_handle_timeout__when_turn_timeout_off_players_turn__should_return_no_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        other_seat = (player.seat + 1) % 4
        _update_round_state(service, "game1", current_player_seat=other_seat)

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.TURN).events
        assert events == []


class TestMahjongGameServiceAfterDiscardRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_discard_has_no_callers_and_wall_is_empty__should_emit_round_end(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        _update_round_state(service, "game1", wall=Wall())

        result = service._process_action_result_internal("game1", _post_discard_result(service, []))
        round_end = [e for e in result if e.event == EventType.ROUND_END]
        assert len(round_end) == 1

    def test_process_action_result__when_ai_answers_resolve_prompt_with_empty_wall__should_end_round(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)
        ai_player_seat = ai_player_seats[0]

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({ai_player_seat}),
            callers=(Caller(seat=ai_player_seat, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt, wall=Wall())

        result = service._process_action_result_internal("game1", _post_discard_result(service, []))
        assert [e.event for e in result] == [EventType.ROUND_END]


class TestMahjongGameServiceProcessAIPlayerFollowupEdgeCases:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_ai_player_followup__when_round_finished__should_return_no_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        result = service._process_ai_player_followup("game1")
        assert result == []

    def test_process_ai_player_followup__when_call_prompt_pending__should_return_no_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({0}),
            callers=(Caller(seat=0, can_ron=True),),
        )
        _update_round_state(
            service,
            "game1",
            current_player_seat=ai_player_seats[0],
            pending_call_prompt=prompt,
        )

        result = service._process_ai_player_followup("game1")
        assert result == []

    def test_process_ai_player_followup__when_ai_has_no_turn_action__should_raise(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)
        _update_round_state(service, "game1", current_player_seat=ai_player_seats[0])

        with (
            patch.object(ai_player_controller, "get_turn_action", return_value=None),
            pytest.raises(GeneratedActionError, match=f"AI seat {ai_player_seats[0]} returned no turn action"),
        ):
            service._process_ai_player_followup("game1")


class TestDispatchAIPlayerCallResponseNonNullAction:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_dispatch_ai_player_call_responses__when_ai_passes__should_clear_pending_prompt(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)
        ai_player_seat = ai_player_seats[0]

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({ai_player_seat}),
            callers=(Caller(seat=ai_player_seat, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        events: list[ServiceEvent] = []
        with patch.object(
            ai_player_controller,
            "get_call_response",
            return_value=(GameAction.PASS, {}),
        ):
            service._dispatch_ai_player_call_responses("game1", prompt, events)

        # AI PASS resolves the prompt
        updated = service._games["game1"].round_state
        assert updated.pending_call_prompt is None


class TestGameEndCleanupSafety:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_action__when_discard_ends_game__should_return_game_end_and_remove_game(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        for seat in range(4):
            _update_player(service, game_id="game1", seat=seat, score=-10000)

        _update_round_state(
            service,
            "game1",
            current_player_seat=player.seat,
            wall=Wall(),
        )

        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")
        tiles = list(player.tiles)
        if len(tiles) < 14:
            tiles.append(0)

        _update_player(service, game_id="game1", seat=player.seat, tiles=tuple(tiles[:14]))
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")
        tile_id = player.tiles[-1]

        waiting = service.get_awaiting("game1")
        update = service.handle_action(
            game_id="game1", seat=player.seat, action=GameAction.DISCARD, data={"tile_id": tile_id}
        )
        game_end_events = [e for e in update.events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert update.awaiting == Awaiting(
            kind=WaitKind.NONE, seats=frozenset(), wait_id=waiting.wait_id + 1, round_number=waiting.round_number
        )
        assert "game1" not in service._games


class TestTurnTimeoutKuikaeIntegration:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_timeout__when_turn_timeout_with_kuikae_restriction__should_discard_tile(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        hand_tiles = list(player.tiles[:11])
        last_tile = hand_tiles[-1]
        kuikae_34 = tile_to_34(last_tile)

        _update_player(
            service,
            game_id="game1",
            seat=player.seat,
            tiles=tuple(hand_tiles),
            kuikae_tiles=(kuikae_34,),
        )
        _update_round_state(service, "game1", current_player_seat=player.seat)

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.TURN).events
        player_discard = events[0].data
        assert isinstance(player_discard, DiscardEvent)
        assert player_discard.seat == player.seat
        assert tile_to_34(player_discard.tile_id) != kuikae_34


class TestServiceGuardClauses:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_ai_player_followup__when_game_has_no_ai_controller__should_return_no_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        del service._ai_player_controllers["game1"]
        assert service._process_ai_player_followup("game1") == []
