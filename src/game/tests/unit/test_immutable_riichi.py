"""
Unit tests for immutable riichi declaration and related mechanics.
"""

from mahjong.tile import TilesConverter

from game.logic.riichi import declare_riichi
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)


class TestDeclareRiichiImmutable:
    def _create_tempai_hand(self) -> tuple[int, ...]:
        """Create a tempai hand."""
        return tuple(TilesConverter.string_to_136_array(man="1123456788899"))

    def _create_game_state(
        self,
        *,
        player_discards: tuple[Discard, ...] | None = None,
        players_with_open_hands: tuple[int, ...] | None = None,
        riichi_sticks: int = 0,
    ) -> tuple[MahjongRoundState, MahjongGameState]:
        """Create game state for testing riichi declaration."""
        player = MahjongPlayer(
            seat=0,
            name="Test",
            tiles=self._create_tempai_hand(),
            score=25000,
            discards=player_discards or (),
        )
        players = (player, *tuple(MahjongPlayer(seat=i, name=f"Bot{i}") for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=tuple(range(10)),
            players=players,
            players_with_open_hands=players_with_open_hands or (),
        )
        game_state = MahjongGameState(
            round_state=round_state,
            riichi_sticks=riichi_sticks,
        )
        return round_state, game_state

    def test_declare_riichi_sets_riichi_flag(self):
        """Declaring riichi sets the is_riichi flag."""
        round_state, game_state = self._create_game_state()
        assert round_state.players[0].is_riichi is False

        new_round_state, _new_game_state = declare_riichi(round_state, game_state, seat=0)

        assert new_round_state.players[0].is_riichi is True
        # original state unchanged
        assert round_state.players[0].is_riichi is False

    def test_declare_riichi_sets_ippatsu_flag(self):
        """Declaring riichi sets the ippatsu flag."""
        round_state, game_state = self._create_game_state()
        assert round_state.players[0].is_ippatsu is False

        new_round_state, _new_game_state = declare_riichi(round_state, game_state, seat=0)

        assert new_round_state.players[0].is_ippatsu is True
        # original state unchanged
        assert round_state.players[0].is_ippatsu is False

    def test_declare_riichi_deducts_1000_points(self):
        """Declaring riichi deducts 1000 points from player."""
        round_state, game_state = self._create_game_state()
        assert round_state.players[0].score == 25000

        new_round_state, _new_game_state = declare_riichi(round_state, game_state, seat=0)

        assert new_round_state.players[0].score == 24000
        # original state unchanged
        assert round_state.players[0].score == 25000

    def test_declare_riichi_increments_riichi_sticks(self):
        """Declaring riichi increments the riichi sticks count."""
        round_state, game_state = self._create_game_state(riichi_sticks=0)

        _new_round_state, new_game_state = declare_riichi(round_state, game_state, seat=0)

        assert new_game_state.riichi_sticks == 1
        # original state unchanged
        assert game_state.riichi_sticks == 0

    def test_declare_riichi_multiple_sticks(self):
        """Multiple riichi declarations accumulate sticks."""
        round_state, game_state = self._create_game_state(riichi_sticks=2)

        _new_round_state, new_game_state = declare_riichi(round_state, game_state, seat=0)

        assert new_game_state.riichi_sticks == 3
        # original state unchanged
        assert game_state.riichi_sticks == 2

    def test_declare_riichi_double_riichi_on_first_turn(self):
        """Declaring riichi on first turn with no open hands is double riichi.

        In the actual game flow, declare_riichi is called AFTER the riichi discard
        is added to player.discards. So for double riichi, len(discards) == 1.
        """
        round_state, game_state = self._create_game_state(
            player_discards=(
                Discard(tile_id=TilesConverter.string_to_136_array(sou="8")[0], is_riichi_discard=True),
            ),  # riichi discard already added
            players_with_open_hands=(),
        )
        assert round_state.players[0].is_daburi is False

        new_round_state, _new_game_state = declare_riichi(round_state, game_state, seat=0)

        assert new_round_state.players[0].is_daburi is True
        # original state unchanged
        assert round_state.players[0].is_daburi is False

    def test_declare_riichi_no_double_riichi_after_first_discard(self):
        """No double riichi if player has already discarded before riichi.

        In the actual game flow, declare_riichi is called AFTER the riichi discard
        is added. So for non-double riichi, len(discards) > 1.
        """
        round_state, game_state = self._create_game_state(
            player_discards=(
                Discard(tile_id=TilesConverter.string_to_136_array(sou="88")[0]),  # previous discard
                Discard(
                    tile_id=TilesConverter.string_to_136_array(sou="88")[1], is_riichi_discard=True
                ),  # riichi discard
            ),
            players_with_open_hands=(),
        )

        new_round_state, _new_game_state = declare_riichi(round_state, game_state, seat=0)

        assert new_round_state.players[0].is_daburi is False

    def test_declare_riichi_no_double_riichi_if_open_hands_exist(self):
        """No double riichi if any player has called an open meld."""
        round_state, game_state = self._create_game_state(
            player_discards=(
                Discard(tile_id=TilesConverter.string_to_136_array(sou="8")[0], is_riichi_discard=True),
            ),  # riichi discard already added
            players_with_open_hands=(1,),  # bot 1 has open hand
        )

        new_round_state, _new_game_state = declare_riichi(round_state, game_state, seat=0)

        assert new_round_state.players[0].is_daburi is False

    def test_declare_riichi_updates_game_state_round_state(self):
        """The new game state should contain the new round state."""
        round_state, game_state = self._create_game_state()

        new_round_state, new_game_state = declare_riichi(round_state, game_state, seat=0)

        # game_state.round_state should be updated to new_round_state
        assert new_game_state.round_state == new_round_state
        assert new_game_state.round_state.players[0].is_riichi is True

    def test_declare_riichi_preserves_other_players(self):
        """Declaring riichi for one player should not affect other players."""
        round_state, game_state = self._create_game_state()

        new_round_state, _new_game_state = declare_riichi(round_state, game_state, seat=0)

        # other players should be unchanged
        for i in range(1, 4):
            assert new_round_state.players[i].is_riichi is False
            assert new_round_state.players[i].is_ippatsu is False
            assert new_round_state.players[i].score == 25000
