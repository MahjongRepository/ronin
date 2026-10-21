import pytest

from game.logic.enums import GameAction, GameErrorCode, RoundPhase, TimeoutType
from game.logic.events import (
    ErrorEvent,
    EventType,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.round_advance import PendingRoundAdvance, RoundAdvanceManager
from game.logic.types import ExhaustiveDrawResult, TenpaiHand
from game.tests.unit.helpers import _find_player, _update_player, _update_round_state


def _make_exhaustive_draw_result() -> ExhaustiveDrawResult:
    return ExhaustiveDrawResult(
        tempai_seats=[0],
        noten_seats=[1, 2, 3],
        tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
    )


class TestPendingRoundAdvance:
    def test_pending_round_advance__when_required_seats_confirmed__should_be_all_confirmed(self):
        pending = PendingRoundAdvance(
            confirmed_seats={0, 1, 2, 3},
            required_seats={0, 1},
        )
        assert pending.all_confirmed is True

    def test_pending_round_advance__when_required_seat_missing__should_not_be_all_confirmed(self):
        pending = PendingRoundAdvance(
            confirmed_seats={0, 2, 3},
            required_seats={0, 1},
        )
        assert pending.all_confirmed is False


class TestRoundAdvanceWaiting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_round_advance__when_round_ends__should_wait_for_human_confirmation(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        result = _make_exhaustive_draw_result()

        events = await service._handle_round_end("game1", result)

        assert events == []
        assert service.is_round_advance_pending("game1")
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")
        unconfirmed = service._round_advance.get_unconfirmed_seats("game1")
        assert player.seat in unconfirmed
        ai_player_controller = service._ai_player_controllers["game1"]
        for seat in ai_player_controller.ai_player_seats:
            assert seat not in unconfirmed

    async def test_round_advance__when_all_players_ai__should_start_next_round_immediately(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        service.replace_with_ai_player("game1", "Player")

        result = _make_exhaustive_draw_result()
        events = await service._handle_round_end("game1", result)

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) >= 4
        assert not service.is_round_advance_pending("game1")


class TestConfirmRound:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_confirm_round__when_last_player_confirms__should_start_next_round(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        events = await service.handle_action("game1", "Player", GameAction.CONFIRM_ROUND, {})

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4
        assert not service.is_round_advance_pending("game1")

    async def test_confirm_round__when_other_player_unconfirmed__should_keep_waiting(self, service):
        await service.start_game("game1", ["Alice", "Bob"])
        game_state = service._games["game1"]
        alice = _find_player(game_state.round_state, "Alice")
        bob = _find_player(game_state.round_state, "Bob")

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        events = await service.handle_action("game1", "Alice", GameAction.CONFIRM_ROUND, {})

        assert events == []
        assert service.is_round_advance_pending("game1")
        unconfirmed = service._round_advance.get_unconfirmed_seats("game1")
        assert alice.seat not in unconfirmed
        assert bob.seat in unconfirmed

    async def test_confirm_round__when_no_advance_pending__should_return_invalid_action_error(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service.handle_action("game1", "Player", GameAction.CONFIRM_ROUND, {})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.INVALID_ACTION

    async def test_game_action__when_round_phase_finished__should_return_invalid_action_error(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")
        tile_id = player.tiles[0]

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        events = await service.handle_action("game1", "Player", GameAction.DISCARD, {"tile_id": tile_id})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.INVALID_ACTION
        assert "not in progress" in events[0].data.message


class TestRoundAdvanceTimeout:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_round_advance_timeout__when_player_times_out__should_auto_confirm_and_advance(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        events = await service.handle_timeout("game1", "Player", TimeoutType.ROUND_ADVANCE)

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4


class TestRoundAdvanceAIPlayerReplacement:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_ai_replacement__when_one_player_disconnects_during_advance__should_confirm_their_seat(self, service):
        await service.start_game("game1", ["Alice", "Bob"])
        game_state = service._games["game1"]
        alice = _find_player(game_state.round_state, "Alice")

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        service.replace_with_ai_player("game1", "Alice")

        events = await service.process_ai_player_actions_after_replacement("game1", alice.seat)

        assert events == []
        assert service.is_round_advance_pending("game1")
        unconfirmed = service._round_advance.get_unconfirmed_seats("game1")
        assert alice.seat not in unconfirmed

    async def test_ai_replacement__when_last_human_disconnects_during_advance__should_start_next_round(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        service.replace_with_ai_player("game1", "Player")

        events = await service.process_ai_player_actions_after_replacement("game1", player.seat)

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) >= 4
        assert not service.is_round_advance_pending("game1")


class TestRoundAdvanceCleanup:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_cleanup_game__when_advance_pending__should_clear_pending(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)
        assert service.is_round_advance_pending("game1")

        service.cleanup_game("game1")

        assert not service.is_round_advance_pending("game1")

    async def test_round_end__when_game_ends__should_not_create_pending_advance(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        _update_player(service, "game1", 0, score=-1000)

        result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            scores={0: -1000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        events = await service._handle_round_end("game1", result)

        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert not service.is_round_advance_pending("game1")


class TestRoundAdvanceHandleRoundEndNone:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_handle_round_end__when_result_none__should_return_missing_round_result_error(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service._handle_round_end("game1", round_result=None)

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert events[0].data.code == GameErrorCode.MISSING_ROUND_RESULT


class TestRoundAdvanceManager:
    @pytest.fixture
    def manager(self):
        return RoundAdvanceManager()

    def test_setup_pending__when_humans_present__should_wait_for_their_seats(self, manager):
        result = manager.setup_pending("g1", ai_player_seats={2, 3})

        assert result is False
        assert manager.is_pending("g1")
        assert manager.get_unconfirmed_seats("g1") == {0, 1}

    def test_setup_pending__when_all_seats_ai__should_advance_without_pending_state(self, manager):
        result = manager.setup_pending("g1", ai_player_seats={0, 1, 2, 3})

        assert result is True
        # No stale pending state -- all AI players means immediate advance
        assert not manager.is_pending("g1")

    def test_setup_pending__when_no_ai_seats__should_wait_for_all_seats(self, manager):
        result = manager.setup_pending("g1", ai_player_seats=set())

        assert result is False
        assert manager.get_unconfirmed_seats("g1") == {0, 1, 2, 3}

    def test_confirm_seat__when_seats_remain__should_return_false(self, manager):
        manager.setup_pending("g1", ai_player_seats={2, 3})

        result = manager.confirm_seat("g1", 0)

        assert result is False
        assert manager.is_pending("g1")
        assert manager.get_unconfirmed_seats("g1") == {1}

    def test_confirm_seat__when_last_seat_confirms__should_complete_and_clear_pending(self, manager):
        manager.setup_pending("g1", ai_player_seats={2, 3})
        manager.confirm_seat("g1", 0)

        result = manager.confirm_seat("g1", 1)

        assert result is True
        assert not manager.is_pending("g1")

    def test_confirm_seat__when_no_pending_advance__should_return_none(self, manager):
        result = manager.confirm_seat("nonexistent", 0)

        assert result is None

    def test_confirm_seat__when_seat_confirmed_twice__should_count_once(self, manager):
        manager.setup_pending("g1", ai_player_seats={2, 3})
        manager.confirm_seat("g1", 0)
        manager.confirm_seat("g1", 0)

        assert manager.get_unconfirmed_seats("g1") == {1}

    def test_cleanup_game__should_remove_pending_advance(self, manager):
        manager.setup_pending("g1", ai_player_seats={2, 3})

        manager.cleanup_game("g1")

        assert not manager.is_pending("g1")

    def test_round_advance_manager__when_multiple_games__should_track_each_independently(self, manager):
        manager.setup_pending("g1", ai_player_seats={2, 3})
        manager.setup_pending("g2", ai_player_seats={1, 2, 3})

        manager.confirm_seat("g2", 0)

        assert manager.is_pending("g1")
        assert not manager.is_pending("g2")
        assert manager.get_unconfirmed_seats("g1") == {0, 1}

    def test_confirm_seat__when_seat_not_required__should_ignore_it(self, manager):
        manager.setup_pending("g1", ai_player_seats={2, 3})

        result = manager.confirm_seat("g1", 2)

        assert result is False
        assert manager.is_pending("g1")
        assert manager.get_unconfirmed_seats("g1") == {0, 1}
