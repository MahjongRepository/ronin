from unittest.mock import patch

import pytest

from game.logic.enums import CallType, GameAction, MeldCallType, PromptKind, RoundPhase, TimeoutType
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DiscardEvent,
    ErrorEvent,
    EventType,
    RoundEndEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.exceptions import GeneratedActionError
from game.logic.mahjong_service import MahjongGameService
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


class TestMahjongGameServiceHandleTimeout:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_timeout__when_meld_timeout_without_pending_prompt__should_return_no_events(self, service):
        player_seat = service.start_game("game1", ["Player"], seed="a" * 192).seats[0]

        events = service.handle_timeout(game_id="game1", seat=player_seat, timeout_type=TimeoutType.MELD)
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

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.MELD)
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

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.TURN)
        assert events == []


class TestMahjongGameServiceCheckAndHandleRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_check_and_handle_round_end__when_round_finished__should_return_true_and_keep_round_end(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)
        round_result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        events = [
            ServiceEvent(
                event=EventType.ROUND_END,
                data=RoundEndEvent(result=round_result, target="all"),
                target=BroadcastTarget(),
            ),
        ]

        result = service._check_and_handle_round_end("game1", events)
        assert result is True
        assert [e.event for e in events] == [EventType.ROUND_END]

    def test_check_and_handle_round_end__when_events_have_no_round_result__should_raise(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        with pytest.raises(AssertionError, match="no round result"):
            service._check_and_handle_round_end("game1", [])


class TestMahjongGameServiceProcessPostDiscard:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_post_discard__when_round_already_finished__should_return_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)
        round_result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        events = [
            ServiceEvent(
                event=EventType.ROUND_END,
                data=RoundEndEvent(result=round_result, target="all"),
                target=BroadcastTarget(),
            ),
        ]

        result = service._process_post_discard("game1", events)
        assert [e.event for e in result] == [EventType.ROUND_END]

    def test_process_post_discard__when_prompt_pending_for_human_player__should_return_events(self, service):
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

        events: list[ServiceEvent] = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    call_type=CallType.MELD,
                    tile_id=0,
                    from_seat=0,
                    callers=[player.seat],
                    target="all",
                ),
                target=SeatTarget(seat=player.seat),
            ),
        ]

        result = service._process_post_discard("game1", events)
        assert [(e.event, e.target) for e in result] == [(EventType.CALL_PROMPT, SeatTarget(seat=player.seat))]

    def test_process_post_discard__when_prompt_pending_only_for_ai_player__should_return_events(self, service):
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

        events: list[ServiceEvent] = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    call_type=CallType.MELD,
                    tile_id=ai_player_tile,
                    from_seat=0,
                    callers=[
                        MeldCaller(
                            seat=ai_player_seat,
                            call_type=MeldCallType.PON,
                        ),
                    ],
                    target="all",
                ),
                target=SeatTarget(seat=ai_player_seat),
            ),
        ]

        result = service._process_post_discard("game1", events)
        assert [e.event for e in result] == [EventType.CALL_PROMPT, EventType.DRAW]

    def test_process_post_discard__when_round_continues__should_draw_for_next_player(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        round_state = game_state.round_state

        current_seat = round_state.current_player_seat
        current_player = round_state.players[current_seat]
        if len(current_player.tiles) > 13:
            _update_player(service, game_id="game1", seat=current_seat, tiles=tuple(list(current_player.tiles)[:13]))

        events: list[ServiceEvent] = []
        result = service._process_post_discard("game1", events)
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

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.TURN)
        assert events[0].data == DiscardEvent(seat=player.seat, tile_id=player_tiles[-1], is_tsumogiri=True)

    def test_handle_timeout__when_turn_timeout_off_players_turn__should_return_no_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        other_seat = (player.seat + 1) % 4
        _update_round_state(service, "game1", current_player_seat=other_seat)

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.TURN)
        assert events == []


class TestMahjongGameServicePostDiscardRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_post_discard__when_wall_is_empty__should_emit_round_end(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        _update_round_state(service, "game1", wall=Wall())

        events: list[ServiceEvent] = []
        result = service._process_post_discard("game1", events)
        round_end = [e for e in result if e.event == EventType.ROUND_END]
        assert len(round_end) == 1

    def test_process_post_discard__when_ai_call_resolves_with_empty_wall__should_return_events(self, service):
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

        events: list[ServiceEvent] = []
        result = service._process_post_discard("game1", events)
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

        events = service.handle_action(
            game_id="game1", seat=player.seat, action=GameAction.DISCARD, data={"tile_id": tile_id}
        )
        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
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

        events = service.handle_timeout(game_id="game1", seat=player.seat, timeout_type=TimeoutType.TURN)
        player_discard = events[0].data
        assert isinstance(player_discard, DiscardEvent)
        assert player_discard.seat == player.seat
        assert tile_to_34(player_discard.tile_id) != kuikae_34


class TestServiceGuardClauses:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_timeout__when_game_does_not_exist__should_return_no_events(self, service):
        assert service.handle_timeout(game_id="nonexistent", seat=0, timeout_type=TimeoutType.TURN) == []

    def test_process_ai_player_followup__when_game_has_no_ai_controller__should_return_no_events(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        del service._ai_player_controllers["game1"]
        assert service._process_ai_player_followup("game1") == []
