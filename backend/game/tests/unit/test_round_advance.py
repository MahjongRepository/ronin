from dataclasses import replace

import pytest

from game.logic.enums import GameAction, GameErrorCode, RoundPhase, TimeoutType, WaitKind
from game.logic.events import (
    ErrorEvent,
    EventType,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.round_advance import PendingRoundAdvance
from game.logic.types import (
    DoubleRonResult,
    DoubleRonWinner,
    ExhaustiveDrawResult,
    HandResultInfo,
    TenpaiHand,
    YakuInfo,
)
from game.tests.unit.helpers import _find_player, _update_player, _update_round_state


def _make_exhaustive_draw_result() -> ExhaustiveDrawResult:
    return ExhaustiveDrawResult(
        tempai_seats=[0],
        noten_seats=[1, 2, 3],
        tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
    )


def _make_double_ron_result() -> DoubleRonResult:
    winners = [
        DoubleRonWinner(
            winner_seat=seat,
            hand_result=HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)], points=1000),
            score_changes={1: -1000, seat: 1000},
            riichi_sticks_collected=0,
            closed_tiles=[],
            melds=[],
        )
        for seat in (2, 0)
    ]
    return DoubleRonResult(
        loser_seat=1,
        winning_tile=0,
        winners=winners,
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 1000, 1: -2000, 2: 1000, 3: 0},
    )


class TestPendingRoundAdvance:
    def test_pending_round_advance__when_seat_confirmed_twice__should_count_once(self):
        pending = PendingRoundAdvance(required_seats=frozenset({0, 1}), results_shown=1)

        pending.confirm(0)
        assert pending.confirm(0) is False
        assert pending.unconfirmed_seats == {1}

    def test_pending_round_advance__when_seat_not_required__should_ignore_it(self):
        pending = PendingRoundAdvance(required_seats=frozenset({0, 1}), results_shown=1)

        assert pending.confirm(2) is False
        assert pending.unconfirmed_seats == {0, 1}


class TestRoundAdvanceWaiting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_round_advance__when_round_ends__should_wait_for_human_confirmation(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        result = _make_exhaustive_draw_result()

        events = service._handle_round_end(runtime, result)
        assert events == []
        assert runtime.pending_confirm is not None

        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")
        unconfirmed = runtime.pending_confirm.unconfirmed_seats
        assert player.seat in unconfirmed
        ai_player_controller = runtime.ai
        for seat in ai_player_controller.ai_player_seats:
            assert seat not in unconfirmed

    def test_round_advance__when_double_ron__should_wait_for_both_results_to_be_shown(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime

        service._handle_round_end(runtime, _make_double_ron_result())

        awaiting = service.get_awaiting(runtime)
        assert awaiting.kind == WaitKind.ROUND_ADVANCE
        assert awaiting.results_shown == 2

    def test_round_end__when_no_seat_is_human__should_raise(self, service):
        start = service.start_game("game1", ["Player"], seed="a" * 192)
        runtime = start.runtime
        service.replace_with_ai_player(runtime, start.seats[0])
        state_before = runtime.state

        with pytest.raises(AssertionError, match="round ended with no human seat"):
            service._handle_round_end(runtime, _make_exhaustive_draw_result())
        assert runtime.state is state_before


class TestConfirmRound:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_confirm_round__when_last_player_confirms__should_start_next_round(self, service):
        start = service.start_game("game1", ["Player"], seed="a" * 192)
        runtime = start.runtime
        player_seat = start.seats[0]

        result = _make_exhaustive_draw_result()
        _update_round_state(runtime, phase=RoundPhase.FINISHED, result=result)
        service._handle_round_end(runtime, result)

        events = service.handle_action(runtime, seat=player_seat, action=GameAction.CONFIRM_ROUND, data={}).events
        round_started = [e for e in events if e.type == EventType.ROUND_STARTED]
        assert len(round_started) == 4
        assert runtime.pending_confirm is None
        assert runtime.state.round_state.result is None

    def test_confirm_round__when_other_player_unconfirmed__should_keep_waiting(self, service):
        runtime = service.start_game("game1", ["Alice", "Bob"]).runtime
        game_state = runtime.state
        alice = _find_player(game_state.round_state, "Alice")
        bob = _find_player(game_state.round_state, "Bob")

        result = _make_exhaustive_draw_result()
        service._handle_round_end(runtime, result)
        waiting = service.get_awaiting(runtime)

        update = service.handle_action(runtime, seat=alice.seat, action=GameAction.CONFIRM_ROUND, data={})
        assert update.events == []
        assert update.awaiting == replace(waiting, seats=frozenset({bob.seat}))
        assert runtime.pending_confirm is not None

        unconfirmed = runtime.pending_confirm.unconfirmed_seats
        assert alice.seat not in unconfirmed
        assert bob.seat in unconfirmed

    def test_confirm_round__when_no_advance_pending__should_return_invalid_action_error(self, service):
        start = service.start_game("game1", ["Player"], seed="a" * 192)
        runtime = start.runtime
        player_seat = start.seats[0]

        events = service.handle_action(runtime, seat=player_seat, action=GameAction.CONFIRM_ROUND, data={}).events
        assert len(events) == 1
        assert events[0].type == EventType.ERROR
        assert isinstance(events[0], ErrorEvent)
        assert events[0].code == GameErrorCode.INVALID_ACTION

    def test_game_action__when_round_phase_finished__should_return_invalid_action_error(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")
        tile_id = player.tiles[0]

        result = _make_exhaustive_draw_result()
        service._handle_round_end(runtime, result)
        _update_round_state(runtime, phase=RoundPhase.FINISHED)

        events = service.handle_action(
            runtime, seat=player.seat, action=GameAction.DISCARD, data={"tile_id": tile_id}
        ).events
        assert len(events) == 1
        assert events[0].type == EventType.ERROR
        assert isinstance(events[0], ErrorEvent)
        assert events[0].code == GameErrorCode.INVALID_ACTION
        assert "not in progress" in events[0].message


class TestRoundAdvanceTimeout:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_round_advance_timeout__when_player_times_out__should_auto_confirm_and_advance(self, service):
        start = service.start_game("game1", ["Player"], seed="a" * 192)
        runtime = start.runtime
        player_seat = start.seats[0]

        result = _make_exhaustive_draw_result()
        service._handle_round_end(runtime, result)

        events = service.handle_timeout(runtime, seat=player_seat, timeout_type=TimeoutType.ROUND_ADVANCE).events
        round_started = [e for e in events if e.type == EventType.ROUND_STARTED]
        assert len(round_started) == 4


class TestRoundAdvanceAIPlayerReplacement:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_ai_replacement__when_one_player_disconnects_during_advance__should_confirm_their_seat(self, service):
        runtime = service.start_game("game1", ["Alice", "Bob"]).runtime
        game_state = runtime.state
        alice = _find_player(game_state.round_state, "Alice")

        result = _make_exhaustive_draw_result()
        service._handle_round_end(runtime, result)

        service.replace_with_ai_player(runtime, alice.seat)
        events = service.process_ai_player_actions_after_replacement(runtime, alice.seat).events
        assert events == []
        assert runtime.pending_confirm is not None

        unconfirmed = runtime.pending_confirm.unconfirmed_seats
        assert alice.seat not in unconfirmed


class TestRoundAdvanceGameEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_round_end__when_game_ends__should_not_create_pending_advance(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        _update_player(runtime, seat=0, score=-1000)

        result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            scores={0: -1000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        events = service._handle_round_end(runtime, result)
        game_end_events = [e for e in events if e.type == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert runtime.pending_confirm is None
