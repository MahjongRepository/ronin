"""
Unit tests for furiten state-change events.

Tests that the server sends FuritenEvent to individual players when their
effective furiten state transitions on/off.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import GameAction, RoundPhase
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import Discard, MahjongPlayer
from game.logic.win import is_effective_furiten
from game.messaging.events import EventType, FuritenEvent, SeatTarget, ServiceEvent
from game.tests.unit.helpers import (
    _find_human_player,
    _update_player,
    _update_round_state,
)


class TestIsEffectiveFuriten:
    """Tests for the is_effective_furiten() helper function."""

    def test_not_furiten_by_default(self):
        player = MahjongPlayer(seat=0, name="P0")
        assert is_effective_furiten(player) is False

    def test_temporary_furiten(self):
        player = MahjongPlayer(seat=0, name="P0", is_temporary_furiten=True)
        assert is_effective_furiten(player) is True

    def test_riichi_furiten(self):
        player = MahjongPlayer(seat=0, name="P0", is_riichi_furiten=True)
        assert is_effective_furiten(player) is True

    def test_discard_furiten(self):
        """Player in tenpai who discarded a waiting tile is in discard furiten."""
        # 123m 456m 789m 12p 55p - waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        tile_3p = TilesConverter.string_to_136_array(pin="3")[0]
        player = MahjongPlayer(
            seat=0,
            name="P0",
            tiles=tuple(tiles),
            discards=(Discard(tile_id=tile_3p),),
        )
        assert is_effective_furiten(player) is True

    def test_temporary_short_circuits_before_expensive_check(self):
        """When temporary furiten is set, discard furiten is not computed."""
        player = MahjongPlayer(
            seat=0,
            name="P0",
            tiles=(),
            is_temporary_furiten=True,
        )
        # No tiles = would fail shanten check, but short-circuits on temporary
        assert is_effective_furiten(player) is True

    def test_not_in_tenpai_not_furiten(self):
        """Player not in tenpai is not furiten even with discards."""
        tiles = TilesConverter.string_to_136_array(man="1234", pin="1234", sou="12345")
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(tiles))
        assert is_effective_furiten(player) is False


class TestFuritenStateTracking:
    """Tests for furiten state tracking in MahjongGameService."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_furiten_state_initialized_on_game_start(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        assert "game1" in service._furiten_state
        assert service._furiten_state["game1"] == {0: False, 1: False, 2: False, 3: False}

    async def test_furiten_state_cleaned_on_game_cleanup(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        service.cleanup_game("game1")
        assert "game1" not in service._furiten_state

    async def test_furiten_state_reset_on_round_start(self, service):
        """Furiten state resets to all False when a new round starts."""
        await service.start_game("game1", ["Human"], seed=2.0)
        # Manually set some furiten state
        service._furiten_state["game1"][0] = True
        service._furiten_state["game1"][2] = True

        # Force a round reset by calling _start_next_round
        # (This requires the game to be in a state that allows it)
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)
        await service._start_next_round("game1")

        assert service._furiten_state["game1"] == {0: False, 1: False, 2: False, 3: False}


class TestCheckFuritenChanges:
    """Tests for _check_furiten_changes method."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_no_event_when_state_unchanged(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        events = service._check_furiten_changes("game1", [0, 1, 2, 3])
        # At game start, all players are not in furiten, state is False -> no change
        assert len(events) == 0

    async def test_event_emitted_on_temporary_furiten(self, service):
        """Setting temporary furiten triggers a furiten event."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        # Set temporary furiten on the human player
        _update_player(service, "game1", human.seat, is_temporary_furiten=True)

        events = service._check_furiten_changes("game1", [human.seat])
        assert len(events) == 1
        assert events[0].event == EventType.FURITEN
        assert isinstance(events[0].data, FuritenEvent)
        assert events[0].data.is_furiten is True
        assert events[0].target == SeatTarget(seat=human.seat)

    async def test_event_emitted_on_furiten_clear(self, service):
        """Clearing furiten triggers a furiten=false event."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        # Set the tracked state to True, then clear the flag
        service._furiten_state["game1"][human.seat] = True
        _update_player(service, "game1", human.seat, is_temporary_furiten=False)

        events = service._check_furiten_changes("game1", [human.seat])
        assert len(events) == 1
        assert events[0].data.is_furiten is False

    async def test_no_duplicate_events(self, service):
        """Same furiten state does not emit duplicate events."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        # Set temporary furiten and check
        _update_player(service, "game1", human.seat, is_temporary_furiten=True)
        events1 = service._check_furiten_changes("game1", [human.seat])
        assert len(events1) == 1

        # Check again without changing state - no new event
        events2 = service._check_furiten_changes("game1", [human.seat])
        assert len(events2) == 0

    async def test_events_only_for_affected_player(self, service):
        """Furiten events target only the affected player, not opponents."""
        await service.start_game("game1", ["Human"], seed=2.0)

        # Set temporary furiten on seat 1 only
        _update_player(service, "game1", 1, is_temporary_furiten=True)

        events = service._check_furiten_changes("game1", [0, 1, 2, 3])
        # Only seat 1 should get an event
        assert len(events) == 1
        assert events[0].target == SeatTarget(seat=1)

    async def test_no_check_when_round_finished(self, service):
        """No furiten check when the round phase is FINISHED."""
        await service.start_game("game1", ["Human"], seed=2.0)
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        # Set furiten on a player
        _update_player(service, "game1", 0, is_temporary_furiten=True)

        events = service._check_furiten_changes("game1", [0])
        assert len(events) == 0

    async def test_no_check_when_game_not_found(self, service):
        events = service._check_furiten_changes("nonexistent", [0])
        assert len(events) == 0

    async def test_riichi_furiten_triggers_event(self, service):
        """Riichi furiten triggers a furiten event."""
        await service.start_game("game1", ["Human"], seed=2.0)

        # Set riichi furiten on seat 2
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
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        if game_state.round_state.current_player_seat != human.seat:
            pytest.skip("Human is not the current player after game start")

        if not human.tiles:
            pytest.skip("Human has no tiles")

        # Pretend the server previously told the client they were in furiten.
        # When handle_action runs and computes furiten=False (the actual state),
        # _append_furiten_changes will detect the True->False transition.
        service._furiten_state["game1"][human.seat] = True

        tile_id = human.tiles[-1]
        events = await service.handle_action("game1", "Human", GameAction.DISCARD, {"tile_id": tile_id})

        # If the round ended (e.g. a bot won), furiten checks are skipped
        round_ended = any(e.event == EventType.ROUND_END for e in events)
        if round_ended:
            pytest.skip("Round ended during discard, furiten check skipped")
            return

        # Verify furiten event was emitted for the human's seat
        furiten_events = [
            e for e in events if e.event == EventType.FURITEN and isinstance(e.data, FuritenEvent)
        ]
        assert len(furiten_events) >= 1
        assert furiten_events[0].data.is_furiten is False
        assert furiten_events[0].target == SeatTarget(seat=human.seat)

    async def test_start_game_no_spurious_furiten_events(self, service):
        """start_game should not produce furiten events (all state is fresh)."""
        events = await service.start_game("game1", ["Human"], seed=2.0)

        furiten_events = [e for e in events if e.event == EventType.FURITEN]
        # At game start, no player should be in furiten
        assert len(furiten_events) == 0

    async def test_append_furiten_changes_skips_when_round_finished(self, service):
        """_append_furiten_changes does nothing when round phase is FINISHED."""
        await service.start_game("game1", ["Human"], seed=2.0)
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        # Set furiten on a player - should not generate events
        _update_player(service, "game1", 0, is_temporary_furiten=True)

        events: list[ServiceEvent] = []
        result = service._append_furiten_changes("game1", events)
        assert len(result) == 0

    async def test_append_furiten_changes_works_when_playing(self, service):
        """_append_furiten_changes emits events when round phase is PLAYING."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        # Ensure round is playing
        assert game_state.round_state.phase == RoundPhase.PLAYING

        # Set furiten on seat 0
        _update_player(service, "game1", 0, is_temporary_furiten=True)

        events: list[ServiceEvent] = []
        result = service._append_furiten_changes("game1", events)
        furiten_events = [e for e in result if e.event == EventType.FURITEN]
        assert len(furiten_events) == 1
        assert furiten_events[0].data.is_furiten is True

    async def test_append_furiten_changes_nonexistent_game(self, service):
        """_append_furiten_changes returns input events when game doesn't exist."""
        events: list[ServiceEvent] = []
        result = service._append_furiten_changes("nonexistent", events)
        assert result == events
