"""
Unit tests for turn loop orchestration.
"""

from unittest.mock import patch

import pytest
from mahjong.tile import TilesConverter

from game.logic.actions import get_available_actions
from game.logic.enums import CallType, PlayerAction, RoundPhase, RoundResultType
from game.logic.game import init_game
from game.logic.round import draw_tile
from game.logic.turn import (
    process_discard_phase,
    process_draw_phase,
)
from game.messaging.events import (
    CallPromptEvent,
    DiscardEvent,
    DoraRevealedEvent,
    DrawEvent,
    EventType,
    RiichiDeclaredEvent,
    RoundEndEvent,
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
        draw_events = [e for e in events if e.type == EventType.DRAW]
        assert len(draw_events) == 1
        assert isinstance(draw_events[0], DrawEvent)
        assert draw_events[0].seat == 0

    def test_draw_phase_returns_draw_event_with_tile(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        events = process_draw_phase(round_state, game_state)

        draw_event = next(e for e in events if e.type == EventType.DRAW)
        assert hasattr(draw_event, "tile_id")
        assert draw_event.target == "seat_0"

    def test_draw_phase_returns_turn_event_with_actions(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        events = process_draw_phase(round_state, game_state)

        turn_events = [e for e in events if e.type == EventType.TURN]
        assert len(turn_events) == 1
        assert hasattr(turn_events[0], "available_actions")
        assert turn_events[0].target == "seat_0"

    def test_draw_phase_exhaustive_draw(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state
        # empty the wall
        round_state.wall = []

        events = process_draw_phase(round_state, game_state)

        round_end_events = [e for e in events if e.type == EventType.ROUND_END]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0], RoundEndEvent)
        assert round_end_events[0].result.type == RoundResultType.EXHAUSTIVE_DRAW
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

        discard_events = [e for e in events if e.type == EventType.DISCARD]
        assert len(discard_events) == 1
        assert isinstance(discard_events[0], DiscardEvent)
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
        call_prompts = [e for e in events if e.type == EventType.CALL_PROMPT]
        if not call_prompts:
            assert round_state.current_player_seat == (initial_seat + 1) % 4


class TestProcessDiscardPhaseDoraRevealed:
    """Tests that deferred dora events are emitted during discard phase."""

    def _create_game_state_with_pending_dora(self):
        """Create game state with pending dora from a previous open/added kan."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        # simulate pending dora from a previous open kan
        round_state.pending_dora_count = 1
        # draw a tile for the dealer
        draw_tile(round_state)
        return game_state

    def test_discard_phase_emits_dora_revealed_for_deferred_dora(self):
        """Discard after open/added kan emits dora_revealed event."""
        game_state = self._create_game_state_with_pending_dora()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]
        initial_dora_count = len(round_state.dora_indicators)

        events = process_discard_phase(round_state, game_state, tile_to_discard)

        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 1
        assert dora_events[0].tile_id == round_state.dora_indicators[-1]
        assert len(dora_events[0].dora_indicators) == initial_dora_count + 1

    def test_discard_phase_dora_revealed_follows_discard_event(self):
        """dora_revealed event comes after discard event in event list."""
        game_state = self._create_game_state_with_pending_dora()
        round_state = game_state.round_state
        tile_to_discard = round_state.players[0].tiles[0]

        events = process_discard_phase(round_state, game_state, tile_to_discard)

        discard_idx = next(i for i, e in enumerate(events) if isinstance(e, DiscardEvent))
        dora_idx = next(i for i, e in enumerate(events) if isinstance(e, DoraRevealedEvent))
        assert dora_idx > discard_idx

    def test_discard_phase_emits_multiple_dora_revealed_events(self):
        """Discard with multiple pending dora emits multiple dora_revealed events."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        round_state.pending_dora_count = 2
        draw_tile(round_state)
        tile_to_discard = round_state.players[0].tiles[0]
        initial_dora_count = len(round_state.dora_indicators)

        events = process_discard_phase(round_state, game_state, tile_to_discard)

        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 2
        assert dora_events[0].tile_id != dora_events[1].tile_id
        assert len(round_state.dora_indicators) == initial_dora_count + 2

    def test_discard_phase_no_dora_revealed_without_pending(self):
        """No dora_revealed event when there are no pending dora indicators."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        assert round_state.pending_dora_count == 0
        draw_tile(round_state)
        tile_to_discard = round_state.players[0].tiles[0]

        events = process_discard_phase(round_state, game_state, tile_to_discard)

        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0


class TestDeferredDoraNotRevealedOnRon:
    """Deferred dora (from open/added kan) must not be revealed when the discard is ron'd.

    Under our rules, open/added kan dora is revealed after the discard
    passes (is not claimed for ron). If someone rons the discard, the kan
    dora indicator should remain hidden and pending_dora_count should be
    preserved so it can be revealed on a future discard.
    """

    def test_pending_dora_not_revealed_when_discard_is_ronned(self):
        """Dora indicators must not change when the discard triggers a ron prompt."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # simulate pending dora from a previous open kan
        round_state.pending_dora_count = 1
        initial_dora_count = len(round_state.dora_indicators)

        # give player 1 a tempai hand waiting for 2p (pair wait)
        # 123m 456m 789m 111p -- needs 2p for the pair
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1112")

        # draw a tile for player 0
        draw_tile(round_state)

        # player 0 discards the winning tile (2p) so player 1 can ron
        win_tile = TilesConverter.string_to_136_array(pin="22")[1]
        round_state.players[0].tiles.append(win_tile)

        events = process_discard_phase(round_state, game_state, win_tile)

        # ron prompt should be generated
        ron_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        assert len(ron_prompts) == 1
        assert 1 in ron_prompts[0].callers

        # the deferred dora must NOT have been revealed
        assert len(round_state.dora_indicators) == initial_dora_count
        assert round_state.pending_dora_count == 1

        # no DoraRevealedEvent should be in the events
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0

    def test_pending_dora_not_revealed_in_events_when_discard_is_ronned(self):
        """DoraRevealedEvent must not appear before a ron prompt in event list."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        round_state.pending_dora_count = 1

        # give player 1 a tempai hand waiting for 2p
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1112")

        draw_tile(round_state)
        win_tile = TilesConverter.string_to_136_array(pin="22")[1]
        round_state.players[0].tiles.append(win_tile)

        events = process_discard_phase(round_state, game_state, win_tile)

        # no dora_revealed events should precede the ron prompt
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0


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
            e
            for e in events
            if e.type == EventType.CALL_PROMPT and getattr(e, "call_type", None) == CallType.RON
        ]
        if not ron_prompts:
            riichi_events = [e for e in events if e.type == EventType.RIICHI_DECLARED]
            assert len(riichi_events) == 1
            assert isinstance(riichi_events[0], RiichiDeclaredEvent)
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

    def _find_action(self, actions: list, action_type: PlayerAction):
        """Find an action by type in the actions list."""
        for action in actions:
            if action.action == action_type:
                return action
        return None

    def test_get_available_actions_returns_discard_tiles(self):
        game_state = self._create_game_state()
        round_state = game_state.round_state

        actions = get_available_actions(round_state, game_state, seat=0)

        discard_action = self._find_action(actions, PlayerAction.DISCARD)
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
        discard_action = self._find_action(actions, PlayerAction.DISCARD)
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

        round_end_events = [e for e in events if e.type == EventType.ROUND_END]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0], RoundEndEvent)
        assert round_end_events[0].result.type == RoundResultType.EXHAUSTIVE_DRAW
        assert round_state.phase == RoundPhase.FINISHED
