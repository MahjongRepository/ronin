"""
Unit tests for round advancement confirmation feature.

Tests PendingRoundAdvance boundary conditions, confirm_round dispatch (single/multi-human,
error paths), timeout auto-confirmation, bot replacement during waiting, cleanup,
start_fixed_timer contracts, and _handle_round_end error path.
"""

import asyncio

import pytest

from game.logic.enums import GameAction, GameErrorCode, RoundPhase, TimeoutType
from game.logic.mahjong_service import MahjongGameService
from game.logic.round_advance import PendingRoundAdvance, RoundAdvanceManager
from game.logic.timer import TimerConfig, TurnTimer
from game.logic.types import ExhaustiveDrawResult
from game.messaging.events import (
    ErrorEvent,
    EventType,
)
from game.tests.unit.helpers import _find_human_player, _update_player, _update_round_state


def _make_exhaustive_draw_result() -> ExhaustiveDrawResult:
    """Create an exhaustive draw result for testing round end."""
    return ExhaustiveDrawResult(
        tempai_seats=[0],
        noten_seats=[1, 2, 3],
        score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
    )


class TestPendingRoundAdvance:
    """Tests for the PendingRoundAdvance dataclass."""

    def test_all_confirmed_when_required_is_subset(self):
        pending = PendingRoundAdvance(
            confirmed_seats={0, 1, 2, 3},
            required_seats={0, 1},
        )
        assert pending.all_confirmed is True

    def test_not_all_confirmed_when_missing(self):
        pending = PendingRoundAdvance(
            confirmed_seats={0, 2, 3},
            required_seats={0, 1},
        )
        assert pending.all_confirmed is False

    def test_all_confirmed_empty_required(self):
        pending = PendingRoundAdvance(
            confirmed_seats={0, 1, 2, 3},
            required_seats=set(),
        )
        assert pending.all_confirmed is True

    def test_idempotent_confirm(self):
        """Adding same seat twice doesn't break anything."""
        pending = PendingRoundAdvance(
            confirmed_seats={0},
            required_seats={0},
        )
        pending.confirmed_seats.add(0)
        assert pending.all_confirmed is True


class TestRoundAdvanceWaiting:
    """Tests that round advancement waits for human confirmation."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_round_end_enters_waiting_state(self, service):
        """After round end, a PendingRoundAdvance is created for human seats."""
        await service.start_game("game1", ["Human"], seed=2.0)
        result = _make_exhaustive_draw_result()

        events = await service._handle_round_end("game1", result)

        assert events == []
        assert service.is_round_advance_pending("game1")
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")
        unconfirmed = service._round_advance.get_unconfirmed_seats("game1")
        assert human.seat in unconfirmed
        bot_controller = service._bot_controllers["game1"]
        for seat in bot_controller.bot_seats:
            assert seat not in unconfirmed

    async def test_all_bots_game_advances_immediately(self, service):
        """When all seats are bots, round advances immediately without waiting."""
        await service.start_game("game1", ["Human"], seed=2.0)

        service.replace_player_with_bot("game1", "Human")

        result = _make_exhaustive_draw_result()
        events = await service._handle_round_end("game1", result)

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) >= 4
        assert not service.is_round_advance_pending("game1")


class TestConfirmRound:
    """Tests for the confirm_round action handling."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_confirm_round_advances_when_all_confirmed(self, service):
        """When all humans confirm, round advances."""
        await service.start_game("game1", ["Human"], seed=2.0)

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        events = await service.handle_action("game1", "Human", GameAction.CONFIRM_ROUND, {})

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4
        assert not service.is_round_advance_pending("game1")

    async def test_partial_confirm_waits(self, service):
        """When only some humans confirm, still waiting."""
        await service.start_game("game1", ["Alice", "Bob"])
        game_state = service._games["game1"]
        alice = _find_human_player(game_state.round_state, "Alice")
        bob = _find_human_player(game_state.round_state, "Bob")

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        events = await service.handle_action("game1", "Alice", GameAction.CONFIRM_ROUND, {})

        assert events == []
        assert service.is_round_advance_pending("game1")
        unconfirmed = service._round_advance.get_unconfirmed_seats("game1")
        assert alice.seat not in unconfirmed
        assert bob.seat in unconfirmed

    async def test_confirm_round_rejected_when_not_pending(self, service):
        """confirm_round returns error when no round is pending."""
        await service.start_game("game1", ["Human"], seed=2.0)

        events = await service.handle_action("game1", "Human", GameAction.CONFIRM_ROUND, {})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.INVALID_ACTION

    async def test_game_actions_rejected_during_finished_phase(self, service):
        """Non-confirm actions are rejected when round phase is FINISHED."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")
        tile_id = human.tiles[0]

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        events = await service.handle_action("game1", "Human", GameAction.DISCARD, {"tile_id": tile_id})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.INVALID_ACTION
        assert "not in progress" in events[0].data.message


class TestRoundAdvanceTimeout:
    """Tests for round advance timeout auto-confirmation."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_timeout_auto_confirms(self, service):
        """ROUND_ADVANCE timeout auto-confirms the player."""
        await service.start_game("game1", ["Human"], seed=2.0)

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        events = await service.handle_timeout("game1", "Human", TimeoutType.ROUND_ADVANCE)

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4


class TestRoundAdvanceBotReplacement:
    """Tests for bot replacement during round-advance waiting."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_disconnect_during_round_advance_auto_confirms(self, service):
        """When human disconnects during waiting, bot replacement auto-confirms."""
        await service.start_game("game1", ["Alice", "Bob"])
        game_state = service._games["game1"]
        alice = _find_human_player(game_state.round_state, "Alice")

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        service.replace_player_with_bot("game1", "Alice")

        events = await service.process_bot_actions_after_replacement("game1", alice.seat)

        assert events == []
        assert service.is_round_advance_pending("game1")
        unconfirmed = service._round_advance.get_unconfirmed_seats("game1")
        assert alice.seat not in unconfirmed

    async def test_last_human_disconnect_advances_round(self, service):
        """When the last human disconnects, all confirm and round advances."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        service.replace_player_with_bot("game1", "Human")

        events = await service.process_bot_actions_after_replacement("game1", human.seat)

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) >= 4
        assert not service.is_round_advance_pending("game1")


class TestRoundAdvanceCleanup:
    """Tests for cleanup of round advance state."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_cleanup_removes_pending_advance(self, service):
        """cleanup_game removes pending advance state."""
        await service.start_game("game1", ["Human"], seed=2.0)
        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)
        assert service.is_round_advance_pending("game1")

        service.cleanup_game("game1")

        assert not service.is_round_advance_pending("game1")

    async def test_game_end_does_not_create_pending_advance(self, service):
        """When game ends (not just round), no pending advance is created."""
        await service.start_game("game1", ["Human"], seed=2.0)

        _update_player(service, "game1", 0, score=-1000)

        result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        events = await service._handle_round_end("game1", result)

        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert not service.is_round_advance_pending("game1")


class TestRoundAdvanceTimerIntegration:
    """Tests for TurnTimer.start_fixed_timer used by round advance."""

    async def test_fixed_timer_fires_callback(self):
        """start_fixed_timer fires the callback after the duration."""
        timer = TurnTimer(TimerConfig(initial_bank_seconds=10.0))
        callback_called = asyncio.Event()

        async def on_timeout():
            callback_called.set()

        timer.start_fixed_timer(0.05, on_timeout)
        await asyncio.wait_for(callback_called.wait(), timeout=1.0)
        assert callback_called.is_set()

    async def test_fixed_timer_does_not_consume_bank(self):
        """start_fixed_timer does not consume bank time."""
        config = TimerConfig(initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        async def on_timeout():
            pass

        timer.start_fixed_timer(0.05, on_timeout)
        await asyncio.sleep(0.1)
        timer.stop()

        assert timer.remaining_bank == 10.0

    async def test_fixed_timer_cancel_does_not_consume_bank(self):
        """Cancelling a fixed timer does not consume bank time."""
        config = TimerConfig(initial_bank_seconds=10.0)
        timer = TurnTimer(config)

        async def on_timeout():
            pass

        timer.start_fixed_timer(1.0, on_timeout)
        await asyncio.sleep(0.05)
        timer.cancel()

        assert timer.remaining_bank == 10.0

    async def test_fixed_timer_cancelled_by_turn_timer(self):
        """Starting a turn timer cancels an active fixed timer."""
        timer = TurnTimer(TimerConfig(initial_bank_seconds=10.0))
        fixed_called = False
        turn_called = False

        async def fixed_callback():
            nonlocal fixed_called
            fixed_called = True

        async def turn_callback():
            nonlocal turn_called
            turn_called = True

        timer.start_fixed_timer(0.5, fixed_callback)
        timer.start_turn_timer(turn_callback)
        timer.cancel()

        await asyncio.sleep(0.1)
        assert fixed_called is False


class TestRoundAdvanceHandleRoundEndNone:
    """Test _handle_round_end with None result still returns error."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_handle_round_end_with_none_result(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        events = await service._handle_round_end("game1", round_result=None)

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert events[0].data.code == GameErrorCode.MISSING_ROUND_RESULT


class TestRoundAdvanceManager:
    """Unit tests for RoundAdvanceManager in isolation."""

    @pytest.fixture
    def manager(self):
        return RoundAdvanceManager()

    def test_setup_pending_with_humans(self, manager):
        """setup_pending creates pending state with human seats as required."""
        result = manager.setup_pending("g1", bot_seats={2, 3})

        assert result is False
        assert manager.is_pending("g1")
        assert manager.get_unconfirmed_seats("g1") == {0, 1}

    def test_setup_pending_all_bots_returns_true(self, manager):
        """setup_pending returns True when all seats are bots (auto-advance)."""
        result = manager.setup_pending("g1", bot_seats={0, 1, 2, 3})

        assert result is True
        # No stale pending state -- all bots means immediate advance
        assert not manager.is_pending("g1")

    def test_setup_pending_no_bots(self, manager):
        """setup_pending with no bots requires all 4 seats to confirm."""
        result = manager.setup_pending("g1", bot_seats=set())

        assert result is False
        assert manager.get_unconfirmed_seats("g1") == {0, 1, 2, 3}

    def test_confirm_seat_partial(self, manager):
        """confirm_seat returns False when others still need to confirm."""
        manager.setup_pending("g1", bot_seats={2, 3})

        result = manager.confirm_seat("g1", 0)

        assert result is False
        assert manager.is_pending("g1")
        assert manager.get_unconfirmed_seats("g1") == {1}

    def test_confirm_seat_completes(self, manager):
        """confirm_seat returns True when all required seats are confirmed."""
        manager.setup_pending("g1", bot_seats={2, 3})
        manager.confirm_seat("g1", 0)

        result = manager.confirm_seat("g1", 1)

        assert result is True
        assert not manager.is_pending("g1")

    def test_confirm_seat_no_pending_returns_none(self, manager):
        """confirm_seat returns None when no pending advance exists."""
        result = manager.confirm_seat("nonexistent", 0)

        assert result is None

    def test_confirm_seat_idempotent(self, manager):
        """Confirming the same seat twice does not break state."""
        manager.setup_pending("g1", bot_seats={2, 3})
        manager.confirm_seat("g1", 0)
        manager.confirm_seat("g1", 0)

        assert manager.get_unconfirmed_seats("g1") == {1}

    def test_is_pending_false_for_unknown_game(self, manager):
        """is_pending returns False for unknown game ids."""
        assert not manager.is_pending("unknown")

    def test_get_unconfirmed_seats_empty_for_unknown_game(self, manager):
        """get_unconfirmed_seats returns empty set for unknown game ids."""
        assert manager.get_unconfirmed_seats("unknown") == set()

    def test_is_seat_required_true(self, manager):
        """is_seat_required returns True for human seats."""
        manager.setup_pending("g1", bot_seats={2, 3})

        assert manager.is_seat_required("g1", 0) is True
        assert manager.is_seat_required("g1", 1) is True

    def test_is_seat_required_false_for_bots(self, manager):
        """is_seat_required returns False for bot seats."""
        manager.setup_pending("g1", bot_seats={2, 3})

        assert manager.is_seat_required("g1", 2) is False
        assert manager.is_seat_required("g1", 3) is False

    def test_is_seat_required_false_for_unknown_game(self, manager):
        """is_seat_required returns False for unknown game ids."""
        assert manager.is_seat_required("unknown", 0) is False

    def test_cleanup_game_removes_pending(self, manager):
        """cleanup_game removes pending state for a game."""
        manager.setup_pending("g1", bot_seats={2, 3})

        manager.cleanup_game("g1")

        assert not manager.is_pending("g1")

    def test_cleanup_game_safe_for_unknown(self, manager):
        """cleanup_game is safe to call for unknown game ids."""
        manager.cleanup_game("unknown")

    def test_multiple_games_independent(self, manager):
        """Multiple games have independent pending state."""
        manager.setup_pending("g1", bot_seats={2, 3})
        manager.setup_pending("g2", bot_seats={1, 2, 3})

        manager.confirm_seat("g2", 0)

        assert manager.is_pending("g1")
        assert not manager.is_pending("g2")
        assert manager.get_unconfirmed_seats("g1") == {0, 1}
