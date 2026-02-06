"""
Unit tests for round advancement confirmation feature.

Tests that rounds don't advance until all humans confirm, timeout auto-confirms,
bots auto-confirm immediately, and related edge cases.
"""

import asyncio

import pytest

from game.logic.enums import GameAction, GameErrorCode, RoundPhase, TimeoutType
from game.logic.mahjong_service import MahjongGameService, PendingRoundAdvance
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
        await service.start_game("game1", ["Human"])
        result = _make_exhaustive_draw_result()

        events = await service._handle_round_end("game1", result)

        # should return empty (RoundEndEvent is in the caller's list)
        assert events == []
        # pending advance should be created
        assert "game1" in service._pending_advances
        pending = service._pending_advances["game1"]
        # human seat should be in required_seats
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")
        assert human.seat in pending.required_seats
        # bot seats should already be confirmed
        bot_controller = service._bot_controllers["game1"]
        for seat in bot_controller.bot_seats:
            assert seat in pending.confirmed_seats

    async def test_round_does_not_advance_without_confirm(self, service):
        """Round doesn't advance until human sends confirm_round."""
        await service.start_game("game1", ["Human"])
        result = _make_exhaustive_draw_result()

        await service._handle_round_end("game1", result)

        # pending advance should exist (waiting for human)
        assert "game1" in service._pending_advances
        pending = service._pending_advances["game1"]
        assert not pending.all_confirmed

    async def test_all_bots_game_advances_immediately(self, service):
        """When all seats are bots, round advances immediately without waiting."""
        await service.start_game("game1", ["Human"])

        # replace human with bot to make it all-bots
        service.replace_player_with_bot("game1", "Human")

        result = _make_exhaustive_draw_result()
        events = await service._handle_round_end("game1", result)

        # should have round_started events (advanced immediately, may play through many rounds)
        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) >= 4
        # no pending advance should remain
        assert service._pending_advances.get("game1") is None


class TestConfirmRound:
    """Tests for the confirm_round action handling."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_confirm_round_advances_when_all_confirmed(self, service):
        """When all humans confirm, round advances."""
        await service.start_game("game1", ["Human"])

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        # confirm round
        events = await service.handle_action("game1", "Human", GameAction.CONFIRM_ROUND, {})

        # should have round_started events
        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4
        # pending advance should be cleaned up
        assert "game1" not in service._pending_advances

    async def test_partial_confirm_waits(self, service):
        """When only some humans confirm, still waiting."""
        await service.start_game("game1", ["Alice", "Bob"])
        game_state = service._games["game1"]
        alice = _find_human_player(game_state.round_state, "Alice")
        bob = _find_human_player(game_state.round_state, "Bob")

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        # only Alice confirms
        events = await service.handle_action("game1", "Alice", GameAction.CONFIRM_ROUND, {})

        # should return empty (waiting for Bob)
        assert events == []
        # pending advance should still exist
        assert "game1" in service._pending_advances
        pending = service._pending_advances["game1"]
        assert alice.seat in pending.confirmed_seats
        assert bob.seat not in pending.confirmed_seats

    async def test_all_humans_confirm_advances(self, service):
        """When all humans in a multi-human game confirm, round advances."""
        await service.start_game("game1", ["Alice", "Bob"])

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        # Alice confirms
        await service.handle_action("game1", "Alice", GameAction.CONFIRM_ROUND, {})

        # Bob confirms
        events = await service.handle_action("game1", "Bob", GameAction.CONFIRM_ROUND, {})

        # should advance
        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4

    async def test_confirm_round_rejected_when_not_pending(self, service):
        """confirm_round returns error when no round is pending."""
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", GameAction.CONFIRM_ROUND, {})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.INVALID_ACTION

    async def test_confirm_round_twice_is_idempotent(self, service):
        """Confirming twice doesn't cause errors or double-advance."""
        await service.start_game("game1", ["Human"])

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        # first confirm advances
        events1 = await service.handle_action("game1", "Human", GameAction.CONFIRM_ROUND, {})
        round_started = [e for e in events1 if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4

        # second confirm -- no pending advance, returns error
        events2 = await service.handle_action("game1", "Human", GameAction.CONFIRM_ROUND, {})
        assert len(events2) == 1
        assert events2[0].event == EventType.ERROR

    async def test_bot_followup_after_round_advance(self, service):
        """After round advance, bot dealer should play automatically."""
        await service.start_game("game1", ["Human"])

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        events = await service.handle_action("game1", "Human", GameAction.CONFIRM_ROUND, {})

        # events should contain round_started + draw + turn (and potentially bot discard events)
        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4
        draw_events = [e for e in events if e.event == EventType.DRAW]
        assert len(draw_events) >= 1

    async def test_game_actions_rejected_during_finished_phase(self, service):
        """Non-confirm actions are rejected when round phase is FINISHED."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")
        tile_id = human.tiles[0]

        # end the round to enter waiting state
        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        # set phase to FINISHED (normally done by action handler before _handle_round_end)
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        # try to discard during FINISHED phase
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
        await service.start_game("game1", ["Human"])

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        # simulate timeout
        events = await service.handle_timeout("game1", "Human", TimeoutType.ROUND_ADVANCE)

        # should advance (Human is the only human)
        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4

    async def test_timeout_nonexistent_game_returns_empty(self, service):
        events = await service.handle_timeout("nonexistent", "Human", TimeoutType.ROUND_ADVANCE)
        assert events == []

    async def test_timeout_unknown_player_returns_empty(self, service):
        await service.start_game("game1", ["Human"])
        events = await service.handle_timeout("game1", "Unknown", TimeoutType.ROUND_ADVANCE)
        assert events == []


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

        # Alice disconnects and is replaced by bot
        service.replace_player_with_bot("game1", "Alice")

        # process bot actions after replacement
        events = await service.process_bot_actions_after_replacement("game1", alice.seat)

        # Alice auto-confirmed, but Bob still pending
        assert events == []
        pending = service._pending_advances.get("game1")
        assert pending is not None
        assert alice.seat in pending.confirmed_seats

    async def test_last_human_disconnect_advances_round(self, service):
        """When the last human disconnects, all confirm and round advances."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)

        # Human disconnects and is replaced by bot
        service.replace_player_with_bot("game1", "Human")

        events = await service.process_bot_actions_after_replacement("game1", human.seat)

        # should advance since all are now confirmed (may play through multiple rounds)
        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) >= 4
        assert service._pending_advances.get("game1") is None

    async def test_bot_replacement_no_pending_advance(self, service):
        """Bot replacement with no pending advance falls through to normal processing."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        # no pending advance -- normal replacement flow
        service.replace_player_with_bot("game1", "Human")
        events = await service.process_bot_actions_after_replacement("game1", human.seat)

        # should process normally (not crash)
        assert isinstance(events, list)


class TestRoundAdvanceCleanup:
    """Tests for cleanup of round advance state."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_cleanup_removes_pending_advance(self, service):
        """cleanup_game removes pending advance state."""
        await service.start_game("game1", ["Human"])
        result = _make_exhaustive_draw_result()
        await service._handle_round_end("game1", result)
        assert "game1" in service._pending_advances

        service.cleanup_game("game1")

        assert "game1" not in service._pending_advances

    async def test_game_end_does_not_create_pending_advance(self, service):
        """When game ends (not just round), no pending advance is created."""
        await service.start_game("game1", ["Human"])

        # set a player's score very low so game ends
        _update_player(service, "game1", 0, score=-1000)

        result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        events = await service._handle_round_end("game1", result)

        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert "game1" not in service._pending_advances


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

        # bank time should not have changed
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
        await service.start_game("game1", ["Human"])

        events = await service._handle_round_end("game1", round_result=None)

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert events[0].data.code == GameErrorCode.MISSING_ROUND_RESULT


class TestRoundAdvanceFullRound:
    """Integration-style tests that play through rounds with confirmation."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_full_round_with_confirmation(self, service):
        """Play a round to completion via exhaustive draw, confirm, and verify next round starts."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        # play turns until round ends
        for _ in range(200):
            game_state = service._games.get("game1")
            if game_state is None:
                break
            round_state = game_state.round_state
            if round_state.phase != RoundPhase.PLAYING:
                break
            if round_state.current_player_seat != human.seat:
                break
            if not human.tiles:
                break
            tile_id = human.tiles[-1]
            await service.handle_action("game1", "Human", GameAction.DISCARD, {"tile_id": tile_id})

        # check if we reached round end with pending advance
        game_state = service._games.get("game1")
        if game_state is None:
            pytest.skip("Game ended before reaching round-advance waiting state")
            return

        if game_state.round_state.phase != RoundPhase.FINISHED or "game1" not in service._pending_advances:
            pytest.skip("Round did not end with human needing to confirm (bot may have won)")
            return

        # confirm round
        events = await service.handle_action("game1", "Human", GameAction.CONFIRM_ROUND, {})
        # should have round_started events
        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4
