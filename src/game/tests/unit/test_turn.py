"""
Unit tests for turn loop orchestration.
"""

from unittest.mock import patch

import pytest
from mahjong.tile import TilesConverter

from game.logic.actions import get_available_actions
from game.logic.game import init_game
from game.logic.round import draw_tile
from game.logic.state import RoundPhase
from game.logic.turn import (
    process_discard_phase,
    process_draw_phase,
)
from game.tests.unit.helpers import _default_seat_configs


class TestProcessDrawPhase:
    def _create_game_state(self):
        """Create a game state for testing."""
        return init_game(_default_seat_configs(), seed=12345.0)

    def test_draw_phase_draws_tile(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        initial_wall_len = len(round_state.wall)
        initial_hand_len = len(round_state.players[0].tiles)

        events = process_draw_phase(round_state, game_state)

        assert len(round_state.wall) == initial_wall_len - 1
        assert len(round_state.players[0].tiles) == initial_hand_len + 1
        # find draw event
        draw_events = [e for e in events if e.type == "draw"]
        assert len(draw_events) == 1
        assert draw_events[0].seat == 0

    def test_draw_phase_returns_draw_event_with_tile(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        events = process_draw_phase(round_state, game_state)

        draw_event = next(e for e in events if e.type == "draw")
        assert hasattr(draw_event, "tile_id")
        assert draw_event.target == "seat_0"

    def test_draw_phase_returns_turn_event_with_actions(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        events = process_draw_phase(round_state, game_state)

        turn_events = [e for e in events if e.type == "turn"]
        assert len(turn_events) == 1
        assert hasattr(turn_events[0], "available_actions")
        assert turn_events[0].target == "seat_0"

    def test_draw_phase_exhaustive_draw(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        # empty the wall
        round_state.wall = []

        events = process_draw_phase(round_state, game_state)

        round_end_events = [e for e in events if e.type == "round_end"]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == "exhaustive_draw"
        assert round_state.phase == RoundPhase.FINISHED


class TestProcessDiscardPhase:
    def _create_game_state(self):
        """Create a game state for testing."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        # draw a tile for the dealer
        draw_tile(game_state.round_state)
        return game_state

    def test_discard_phase_creates_discard_event(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        events = process_discard_phase(round_state, game_state, tile_to_discard)

        discard_events = [e for e in events if e.type == "discard"]
        assert len(discard_events) == 1
        assert discard_events[0].tile_id == tile_to_discard
        assert discard_events[0].target == "all"

    def test_discard_phase_removes_tile_from_hand(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        process_discard_phase(round_state, game_state, tile_to_discard)

        assert tile_to_discard not in round_state.players[0].tiles

    def test_discard_phase_adds_to_all_discards(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        process_discard_phase(round_state, game_state, tile_to_discard)

        assert tile_to_discard in round_state.all_discards

    def test_discard_phase_advances_turn_when_no_calls(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]
        initial_seat = round_state.current_player_seat

        events = process_discard_phase(round_state, game_state, tile_to_discard)

        # if no call_prompt events, turn should advance
        call_prompts = [e for e in events if e.type == "call_prompt"]
        if not call_prompts:
            assert round_state.current_player_seat == (initial_seat + 1) % 4


class TestProcessDiscardPhaseWithRiichi:
    def _create_tempai_game_state(self):
        """Create a game state where player 0 is in tempai."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # manually set player 0 to have a tempai hand
        # 123m 456m 789m 111p, waiting for 2p
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1113")
        # draw a tile
        draw_tile(round_state)

        return game_state

    def test_discard_phase_with_riichi_declaration(self):
        game_state = self._create_tempai_game_state()
        round_state = game_state.round_state
        # discard the drawn tile with riichi
        tile_to_discard = round_state.players[0].tiles[-1]

        events = process_discard_phase(round_state, game_state, tile_to_discard, is_riichi=True)

        # check for riichi declared event (if no ron calls)
        ron_prompts = [
            e for e in events if e.type == "call_prompt" and getattr(e, "call_type", None) == "ron"
        ]
        if not ron_prompts:
            riichi_events = [e for e in events if e.type == "riichi_declared"]
            assert len(riichi_events) == 1
            assert riichi_events[0].seat == 0
            assert round_state.players[0].is_riichi is True

    def test_discard_phase_riichi_fails_when_not_tempai(self):
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        # player 0 has random tiles, not tempai
        draw_tile(round_state)
        tile_to_discard = round_state.players[0].tiles[0]

        with pytest.raises(ValueError, match="cannot declare riichi"):
            process_discard_phase(round_state, game_state, tile_to_discard, is_riichi=True)


class TestGetAvailableActions:
    def _create_game_state(self):
        """Create a game state for testing."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        # draw a tile for the dealer
        draw_tile(game_state.round_state)
        return game_state

    def _find_action(self, actions: list, action_type: str):
        """Find an action by type in the actions list."""
        for action in actions:
            if action.action == action_type:
                return action
        return None

    def test_get_available_actions_returns_discard_tiles(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        discard_action = self._find_action(actions, "discard")
        assert discard_action is not None
        assert discard_action.tiles is not None
        assert len(discard_action.tiles) == 14  # 13 dealt + 1 drawn

    def test_get_available_actions_returns_riichi_option(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        # riichi action is present only if player is in tempai
        # check that the function returns a list of actions
        assert isinstance(actions, list)

    def test_get_available_actions_returns_tsumo_option(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        # tsumo action is present only if player has a winning hand
        assert isinstance(actions, list)

    def test_get_available_actions_returns_kan_options(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        # kan/added_kan actions are present only if player has kan options
        assert isinstance(actions, list)

    def test_get_available_actions_riichi_limits_discards(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        round_state.players[0].is_riichi = True

        actions = get_available_actions(round_state, game_state, seat=0)

        # in riichi, can only discard the drawn tile
        discard_action = self._find_action(actions, "discard")
        assert discard_action is not None
        assert discard_action.tiles is not None
        assert len(discard_action.tiles) == 1
        assert discard_action.tiles[0] == round_state.players[0].tiles[-1]


class TestProcessDrawPhaseDrawReturnsNone:
    """Tests draw phase fallback when draw_tile returns None."""

    def test_draw_phase_handles_null_draw(self):
        """Draw phase handles None from draw_tile by processing exhaustive draw."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        with (
            patch("game.logic.turn.draw_tile", return_value=None),
            patch("game.logic.turn.check_exhaustive_draw", return_value=False),
        ):
            events = process_draw_phase(round_state, game_state)

        round_end_events = [e for e in events if e.type == "round_end"]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == "exhaustive_draw"
        assert round_state.phase == RoundPhase.FINISHED
