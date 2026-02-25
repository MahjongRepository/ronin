"""
Unit tests for round advancement confirmation feature.

Tests PendingRoundAdvance boundary conditions, confirm_round dispatch (single/multi-player,
error paths), timeout auto-confirmation, AI player replacement during waiting, cleanup,
and _handle_round_end error path.
"""

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
    """Create an exhaustive draw result for testing round end."""
    return ExhaustiveDrawResult(
        tempai_seats=[0],
        noten_seats=[1, 2, 3],
        tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
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


class TestRoundAdvanceWaiting:
    """Tests that round advancement waits for player confirmation."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_round_end_enters_waiting_state(self, service):
        """After round end, a PendingRoundAdvance is created for player seats."""
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

    async def test_all_ai_players_game_advances_immediately(self, service):
        """When all seats are AI players, round advances immediately without waiting."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        service.replace_with_ai_player("game1", "Player")

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
        """When all players confirm, round advances."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        events = await service.handle_action("game1", "Player", GameAction.CONFIRM_ROUND, {})

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4
        assert not service.is_round_advance_pending("game1")

    async def test_partial_confirm_waits(self, service):
        """When only some players confirm, still waiting."""
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

    async def test_confirm_round_rejected_when_not_pending(self, service):
        """confirm_round returns error when no round is pending."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service.handle_action("game1", "Player", GameAction.CONFIRM_ROUND, {})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.INVALID_ACTION

    async def test_game_actions_rejected_during_finished_phase(self, service):
        """Non-confirm actions are rejected when round phase is FINISHED."""
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
    """Tests for round advance timeout auto-confirmation."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_timeout_auto_confirms(self, service):
        """ROUND_ADVANCE timeout auto-confirms the player."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        events = await service.handle_timeout("game1", "Player", TimeoutType.ROUND_ADVANCE)

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4


class TestRoundAdvanceAIPlayerReplacement:
    """Tests for AI player replacement during round-advance waiting."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_disconnect_during_round_advance_auto_confirms(self, service):
        """When player disconnects during waiting, AI player replacement auto-confirms."""
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

    async def test_last_player_disconnect_advances_round(self, service):
        """When the last player disconnects, all confirm and round advances."""
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
    """Tests for cleanup of round advance state."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_cleanup_removes_pending_advance(self, service):
        """cleanup_game removes pending advance state."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)
        assert service.is_round_advance_pending("game1")

        service.cleanup_game("game1")

        assert not service.is_round_advance_pending("game1")

    async def test_game_end_does_not_create_pending_advance(self, service):
        """When game ends (not just round), no pending advance is created."""
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
    """Test _handle_round_end with None result still returns error."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_handle_round_end_with_none_result(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service._handle_round_end("game1", round_result=None)

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert events[0].data.code == GameErrorCode.MISSING_ROUND_RESULT


class TestRoundAdvanceManager:
    """Unit tests for RoundAdvanceManager in isolation."""

    @pytest.fixture
    def manager(self):
        return RoundAdvanceManager()

    def test_setup_pending_with_players(self, manager):
        """setup_pending creates pending state with player seats as required."""
        result = manager.setup_pending("g1", ai_player_seats={2, 3})

        assert result is False
        assert manager.is_pending("g1")
        assert manager.get_unconfirmed_seats("g1") == {0, 1}

    def test_setup_pending_all_ai_players_returns_true(self, manager):
        """setup_pending returns True when all seats are AI players (auto-advance)."""
        result = manager.setup_pending("g1", ai_player_seats={0, 1, 2, 3})

        assert result is True
        # No stale pending state -- all AI players means immediate advance
        assert not manager.is_pending("g1")

    def test_setup_pending_no_ai_players(self, manager):
        """setup_pending with no AI players requires all 4 seats to confirm."""
        result = manager.setup_pending("g1", ai_player_seats=set())

        assert result is False
        assert manager.get_unconfirmed_seats("g1") == {0, 1, 2, 3}

    def test_confirm_seat_partial(self, manager):
        """confirm_seat returns False when others still need to confirm."""
        manager.setup_pending("g1", ai_player_seats={2, 3})

        result = manager.confirm_seat("g1", 0)

        assert result is False
        assert manager.is_pending("g1")
        assert manager.get_unconfirmed_seats("g1") == {1}

    def test_confirm_seat_completes(self, manager):
        """confirm_seat returns True when all required seats are confirmed."""
        manager.setup_pending("g1", ai_player_seats={2, 3})
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
        manager.setup_pending("g1", ai_player_seats={2, 3})
        manager.confirm_seat("g1", 0)
        manager.confirm_seat("g1", 0)

        assert manager.get_unconfirmed_seats("g1") == {1}

    def test_cleanup_game_removes_pending(self, manager):
        """cleanup_game removes pending state for a game."""
        manager.setup_pending("g1", ai_player_seats={2, 3})

        manager.cleanup_game("g1")

        assert not manager.is_pending("g1")

    def test_multiple_games_independent(self, manager):
        """Multiple games have independent pending state."""
        manager.setup_pending("g1", ai_player_seats={2, 3})
        manager.setup_pending("g2", ai_player_seats={1, 2, 3})

        manager.confirm_seat("g2", 0)

        assert manager.is_pending("g1")
        assert not manager.is_pending("g2")
        assert manager.get_unconfirmed_seats("g1") == {0, 1}

    def test_confirm_seat_rejects_non_required_seat(self, manager):
        """confirm_seat returns False for seats not in the required set (e.g. AI seats)."""
        manager.setup_pending("g1", ai_player_seats={2, 3})

        result = manager.confirm_seat("g1", 2)

        assert result is False
        assert manager.is_pending("g1")
        assert manager.get_unconfirmed_seats("g1") == {0, 1}
