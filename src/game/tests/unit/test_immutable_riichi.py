"""
Unit tests for immutable riichi declaration edge cases.

Tests basic riichi mechanics (flag setting, point deduction, stick increment)
are covered by integration tests in test_game_flow.py::TestRiichiAndIppatsu.
This file focuses on double riichi (daburi) logic requiring specific state
construction not achievable via replays.
"""

from mahjong.tile import TilesConverter

from game.logic.riichi import declare_riichi
from game.logic.settings import GameSettings
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)


class TestDeclareRiichiDaburi:
    """Tests for double riichi (daburi) edge cases."""

    def _create_tempai_hand(self) -> tuple[int, ...]:
        """Create a tempai hand."""
        return tuple(TilesConverter.string_to_136_array(man="1123456788899"))

    def _create_game_state(
        self,
        *,
        player_discards: tuple[Discard, ...] | None = None,
        players_with_open_hands: tuple[int, ...] | None = None,
    ) -> tuple[MahjongRoundState, MahjongGameState]:
        """Create game state for testing riichi declaration."""
        player = MahjongPlayer(
            seat=0,
            name="Test",
            tiles=self._create_tempai_hand(),
            score=25000,
            discards=player_discards or (),
        )
        players = (player, *tuple(MahjongPlayer(seat=i, name=f"Bot{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=tuple(range(10)),
            players=players,
            players_with_open_hands=players_with_open_hands or (),
        )
        game_state = MahjongGameState(
            round_state=round_state,
        )
        return round_state, game_state

    def test_double_riichi_on_first_turn(self):
        """Declaring riichi on first turn with no open hands is double riichi.

        In the actual game flow, declare_riichi is called AFTER the riichi discard
        is added to player.discards. So for double riichi, len(discards) == 1.
        """
        round_state, game_state = self._create_game_state(
            player_discards=(
                Discard(tile_id=TilesConverter.string_to_136_array(sou="8")[0], is_riichi_discard=True),
            ),
            players_with_open_hands=(),
        )
        assert round_state.players[0].is_daburi is False

        settings = GameSettings()
        new_round_state, _new_game_state = declare_riichi(
            round_state,
            game_state,
            seat=0,
            settings=settings,
        )

        assert new_round_state.players[0].is_daburi is True
        # original state unchanged
        assert round_state.players[0].is_daburi is False

    def test_no_double_riichi_after_first_discard(self):
        """No double riichi if player has already discarded before riichi.

        In the actual game flow, declare_riichi is called AFTER the riichi discard
        is added. So for non-double riichi, len(discards) > 1.
        """
        round_state, game_state = self._create_game_state(
            player_discards=(
                Discard(tile_id=TilesConverter.string_to_136_array(sou="88")[0]),
                Discard(tile_id=TilesConverter.string_to_136_array(sou="88")[1], is_riichi_discard=True),
            ),
            players_with_open_hands=(),
        )

        settings = GameSettings()
        new_round_state, _new_game_state = declare_riichi(
            round_state,
            game_state,
            seat=0,
            settings=settings,
        )

        assert new_round_state.players[0].is_daburi is False

    def test_no_double_riichi_if_open_hands_exist(self):
        """No double riichi if any player has called an open meld."""
        round_state, game_state = self._create_game_state(
            player_discards=(
                Discard(tile_id=TilesConverter.string_to_136_array(sou="8")[0], is_riichi_discard=True),
            ),
            players_with_open_hands=(1,),
        )

        settings = GameSettings()
        new_round_state, _new_game_state = declare_riichi(
            round_state,
            game_state,
            seat=0,
            settings=settings,
        )

        assert new_round_state.players[0].is_daburi is False
