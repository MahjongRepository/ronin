"""
Unit tests for immutable turn processing edge cases.

Covers:
- emit_deferred_dora_events: pending dora reveal mechanics (single, none, multiple)
- process_discard_phase: riichi declaration error when not tempai
- process_tsumo_call: tsumo declaration error when not winning hand

Basic turn processing (draw, discard, ron, meld) and immutability contracts
are covered by integration tests in test_game_flow.py and edge case tests
in test_turn_edge_cases.py.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import RoundPhase
from game.logic.events import DoraRevealedEvent
from game.logic.exceptions import InvalidRiichiError, InvalidWinError
from game.logic.turn import (
    emit_deferred_dora_events,
    process_discard_phase,
    process_tsumo_call,
)
from game.tests.conftest import create_game_state, create_player, create_round_state


def _default_round_state(pending_dora_count: int = 0):
    """Create a round state with a standard wall and dead wall for dora tests."""
    wall = tuple(TilesConverter.string_to_136_array(man="1111222233334444"))
    dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
    all_tiles = TilesConverter.string_to_136_array(man="123456789", pin="111")
    players = tuple(
        create_player(
            seat=i,
            tiles=tuple(all_tiles[i * 3 : (i + 1) * 3 + 10]),
        )
        for i in range(4)
    )
    return create_round_state(
        players=players,
        wall=wall,
        dead_wall=dead_wall,
        dora_indicators=(dead_wall[2],),
        pending_dora_count=pending_dora_count,
        phase=RoundPhase.PLAYING,
    )


class TestEmitDeferredDoraEventsImmutable:
    def test_emit_deferred_dora_events_with_pending_dora(self):
        """Pending dora should be revealed and emitted as events."""
        round_state = _default_round_state(pending_dora_count=1)
        initial_dora_count = len(round_state.wall.dora_indicators)

        new_state, events = emit_deferred_dora_events(round_state)

        assert len(new_state.wall.dora_indicators) == initial_dora_count + 1
        assert new_state.wall.pending_dora_count == 0
        assert len(events) == 1
        assert isinstance(events[0], DoraRevealedEvent)
        # original state unchanged
        assert len(round_state.wall.dora_indicators) == initial_dora_count
        assert round_state.wall.pending_dora_count == 1

    def test_emit_deferred_dora_events_no_pending_dora(self):
        """No events should be emitted when pending_dora_count is 0."""
        round_state = _default_round_state(pending_dora_count=0)

        new_state, events = emit_deferred_dora_events(round_state)

        assert new_state.wall.dora_indicators == round_state.wall.dora_indicators
        assert len(events) == 0

    def test_emit_deferred_dora_events_multiple_pending(self):
        """Multiple pending dora should all be revealed."""
        round_state = _default_round_state(pending_dora_count=2)
        initial_dora_count = len(round_state.wall.dora_indicators)

        new_state, events = emit_deferred_dora_events(round_state)

        assert len(new_state.wall.dora_indicators) == initial_dora_count + 2
        assert new_state.wall.pending_dora_count == 0
        assert len(events) == 2
        assert all(isinstance(e, DoraRevealedEvent) for e in events)


class TestDiscardPhaseRiichiError:
    def test_discard_phase_riichi_fails_when_not_tempai(self):
        """Discard phase with riichi should fail when player is not tempai."""
        # non-tempai hand
        tiles = tuple(TilesConverter.string_to_136_array(man="135789", pin="246")[:14])
        players = tuple(create_player(seat=i, tiles=tiles if i == 0 else ()) for i in range(4))
        wall = tuple(TilesConverter.string_to_136_array(man="1111222233334444"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
        )
        game_state = create_game_state(round_state)
        tile_to_discard = round_state.players[0].tiles[0]

        with pytest.raises(InvalidRiichiError, match="cannot declare riichi"):
            process_discard_phase(round_state, game_state, tile_to_discard, is_riichi=True)


class TestTsumoCallError:
    def test_tsumo_call_fails_when_not_winning_hand(self):
        """Tsumo call should fail when player doesn't have a winning hand."""
        # non-winning hand
        tiles = tuple(TilesConverter.string_to_136_array(man="13579", pin="2468", sou="135")[:13])
        players = tuple(create_player(seat=i, tiles=tiles if i == 0 else ()) for i in range(4))
        wall = tuple(TilesConverter.string_to_136_array(man="1111222233334444"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = create_round_state(
            players=players,
            wall=wall,
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
        )
        game_state = create_game_state(round_state)

        with pytest.raises(InvalidWinError, match="cannot declare tsumo"):
            process_tsumo_call(round_state, game_state, winner_seat=0)
