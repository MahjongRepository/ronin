"""
Unit tests for furiten state-change events.

Tests that the server sends FuritenEvent to individual players when their
effective furiten state transitions on/off.
"""

import pytest

from game.logic.enums import GameAction, RoundPhase
from game.logic.events import EventType, FuritenEvent, SeatTarget, ServiceEvent
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import MahjongPlayer
from game.logic.win import is_effective_furiten
from game.tests.unit.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)


class TestIsEffectiveFuriten:
    """Tests for the is_effective_furiten() helper function."""

    def test_temporary_furiten(self):
        player = MahjongPlayer(seat=0, name="P0", is_temporary_furiten=True, score=25000)
        assert is_effective_furiten(player) is True

    def test_riichi_furiten(self):
        player = MahjongPlayer(seat=0, name="P0", is_riichi_furiten=True, score=25000)
        assert is_effective_furiten(player) is True


class TestCheckFuritenChanges:
    """Tests for _check_furiten_changes method."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_no_event_when_state_unchanged(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        events = service._check_furiten_changes("game1", [0, 1, 2, 3])
        assert len(events) == 0

    async def test_event_emitted_on_temporary_furiten(self, service):
        """Setting temporary furiten triggers a furiten event."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        _update_player(service, "game1", player.seat, is_temporary_furiten=True)

        events = service._check_furiten_changes("game1", [player.seat])
        assert len(events) == 1
        assert events[0].event == EventType.FURITEN
        assert isinstance(events[0].data, FuritenEvent)
        assert events[0].data.is_furiten is True
        assert events[0].target == SeatTarget(seat=player.seat)

    async def test_event_emitted_on_furiten_clear(self, service):
        """Clearing furiten triggers a furiten=false event."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        service._furiten_state["game1"][player.seat] = True
        _update_player(service, "game1", player.seat, is_temporary_furiten=False)

        events = service._check_furiten_changes("game1", [player.seat])
        assert len(events) == 1
        assert events[0].data.is_furiten is False

    async def test_no_duplicate_events(self, service):
        """Same furiten state does not emit duplicate events."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        _update_player(service, "game1", player.seat, is_temporary_furiten=True)
        events1 = service._check_furiten_changes("game1", [player.seat])
        assert len(events1) == 1

        events2 = service._check_furiten_changes("game1", [player.seat])
        assert len(events2) == 0

    async def test_events_only_for_affected_player(self, service):
        """Furiten events target only the affected player, not opponents."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        _update_player(service, "game1", 1, is_temporary_furiten=True)

        events = service._check_furiten_changes("game1", [0, 1, 2, 3])
        assert len(events) == 1
        assert events[0].target == SeatTarget(seat=1)

    async def test_no_check_when_round_finished(self, service):
        """No furiten check when the round phase is FINISHED."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        _update_player(service, "game1", 0, is_temporary_furiten=True)

        events = service._check_furiten_changes("game1", [0])
        assert len(events) == 0

    async def test_no_check_when_game_not_found(self, service):
        events = service._check_furiten_changes("nonexistent", [0])
        assert len(events) == 0

    async def test_riichi_furiten_triggers_event(self, service):
        """Riichi furiten triggers a furiten event."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        _update_player(service, "game1", 2, is_riichi_furiten=True)

        events = service._check_furiten_changes("game1", [2])
        assert len(events) == 1
        assert events[0].data.is_furiten is True
        assert events[0].target == SeatTarget(seat=2)


class TestFuritenEventsInGameFlow:
    """Integration-style tests that furiten events are emitted during gameplay."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_furiten_events_in_action_flow(self, service):
        """Furiten events are emitted through handle_action when state changes."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        if game_state.round_state.current_player_seat != player.seat:
            pytest.skip("Player is not the current player after game start")

        if not player.tiles:
            pytest.skip("Player has no tiles")

        # Pretend the server previously told the client they were in furiten.
        # When handle_action runs and computes furiten=False (the actual state),
        # _append_furiten_changes will detect the True->False transition.
        service._furiten_state["game1"][player.seat] = True

        tile_id = player.tiles[-1]
        events = await service.handle_action("game1", "Player", GameAction.DISCARD, {"tile_id": tile_id})

        round_ended = any(e.event == EventType.ROUND_END for e in events)
        if round_ended:
            pytest.skip("Round ended during discard, furiten check skipped")
            return

        furiten_events = [e for e in events if e.event == EventType.FURITEN and isinstance(e.data, FuritenEvent)]
        assert len(furiten_events) >= 1
        assert furiten_events[0].data.is_furiten is False
        assert furiten_events[0].target == SeatTarget(seat=player.seat)

    async def test_start_game_no_spurious_furiten_events(self, service):
        """start_game should not produce furiten events (all state is fresh)."""
        events = await service.start_game("game1", ["Player"], seed="a" * 192)

        furiten_events = [e for e in events if e.event == EventType.FURITEN]
        assert len(furiten_events) == 0

    async def test_append_furiten_changes_works_when_playing(self, service):
        """_append_furiten_changes emits events when round phase is PLAYING."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]

        assert game_state.round_state.phase == RoundPhase.PLAYING

        _update_player(service, "game1", 0, is_temporary_furiten=True)

        events: list[ServiceEvent] = []
        result = service._append_furiten_changes("game1", events)
        furiten_events = [e for e in result if e.event == EventType.FURITEN]
        assert len(furiten_events) == 1
        assert furiten_events[0].data.is_furiten is True
