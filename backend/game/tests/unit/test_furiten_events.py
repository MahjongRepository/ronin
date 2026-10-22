import pytest

from game.logic.enums import GameAction, RoundPhase
from game.logic.events import EventType, FuritenEvent, SeatTarget
from game.logic.mahjong_service import MahjongGameService
from game.tests.unit.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)


class TestCheckFuritenChanges:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_check_furiten_changes__when_state_unchanged__should_emit_nothing(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]

        events = service._furiten_tracker.check_changes("game1", game_state.round_state)
        assert len(events) == 0

    def test_check_furiten_changes__when_temporary_furiten_starts__should_emit_furiten_event(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")
        _update_player(service, game_id="game1", seat=player.seat, is_temporary_furiten=True)

        game_state = service._games["game1"]
        events = service._furiten_tracker.check_changes("game1", game_state.round_state)
        assert len(events) == 1
        assert events[0].event == EventType.FURITEN
        assert isinstance(events[0].data, FuritenEvent)
        assert events[0].data.is_furiten is True
        assert events[0].target == SeatTarget(seat=player.seat)

    def test_check_furiten_changes__when_furiten_clears__should_emit_event_with_false(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        service._furiten_tracker._state["game1"][player.seat] = True
        _update_player(service, game_id="game1", seat=player.seat, is_temporary_furiten=False)

        game_state = service._games["game1"]
        events = service._furiten_tracker.check_changes("game1", game_state.round_state)
        assert len(events) == 1
        assert events[0].data.is_furiten is False

    def test_check_furiten_changes__when_called_twice__should_emit_once(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        _update_player(service, game_id="game1", seat=player.seat, is_temporary_furiten=True)
        game_state = service._games["game1"]
        events1 = service._furiten_tracker.check_changes("game1", game_state.round_state)
        assert len(events1) == 1

        events2 = service._furiten_tracker.check_changes("game1", game_state.round_state)
        assert len(events2) == 0

    def test_check_furiten_changes__when_one_player_changes__should_target_only_that_seat(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        _update_player(service, game_id="game1", seat=1, is_temporary_furiten=True)

        game_state = service._games["game1"]
        events = service._furiten_tracker.check_changes("game1", game_state.round_state)
        assert len(events) == 1
        assert events[0].target == SeatTarget(seat=1)

    def test_check_furiten_changes__when_round_finished__should_emit_nothing(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)
        _update_player(service, game_id="game1", seat=0, is_temporary_furiten=True)

        game_state = service._games["game1"]
        events = service._furiten_tracker.check_changes("game1", game_state.round_state)
        assert len(events) == 0

    def test_check_furiten_changes__when_game_unknown__should_emit_nothing(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]

        events = service._furiten_tracker.check_changes("nonexistent", game_state.round_state)
        assert len(events) == 0

    def test_check_furiten_changes__when_riichi_furiten_starts__should_emit_furiten_event(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        _update_player(service, game_id="game1", seat=2, is_riichi_furiten=True)

        game_state = service._games["game1"]
        events = service._furiten_tracker.check_changes("game1", game_state.round_state)
        assert len(events) == 1
        assert events[0].data.is_furiten is True
        assert events[0].target == SeatTarget(seat=2)


class TestFuritenEventsInGameFlow:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_furiten_events__when_action_changes_furiten__should_emit_event_to_player(self, service):
        service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")
        assert game_state.round_state.current_player_seat == player.seat

        # Pretend the server previously told the client they were in furiten.
        # When handle_action runs and computes furiten=False (the actual state),
        # _append_furiten_changes will detect the True->False transition.
        service._furiten_tracker._state["game1"][player.seat] = True
        tile_id = player.tiles[-1]
        events = service.handle_action(
            game_id="game1", player_name="Player", action=GameAction.DISCARD, data={"tile_id": tile_id}
        )
        furiten_events = [e for e in events if e.event == EventType.FURITEN and isinstance(e.data, FuritenEvent)]
        assert len(furiten_events) == 1
        assert furiten_events[0].data.is_furiten is False
        assert furiten_events[0].target == SeatTarget(seat=player.seat)

    def test_furiten_events__when_game_starts__should_emit_none(self, service):
        events = service.start_game("game1", ["Player"], seed="a" * 192)
        furiten_events = [e for e in events if e.event == EventType.FURITEN]
        assert len(furiten_events) == 0
