"""
Unit tests for riichi declaration and related mechanics.
"""

from mahjong.meld import Meld

from game.logic.riichi import (
    FIRST_URA_DORA_INDEX,
    can_declare_riichi,
    declare_riichi,
    get_ura_dora,
)
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)


class TestCanDeclareRiichi:
    def _create_tempai_hand(self) -> list[int]:
        """
        Create a tempai hand: 11m 234m 567m 888m 9m, waiting for 9m pair.
        """
        return [0, 1, 4, 8, 12, 16, 20, 24, 28, 29, 30, 32, 33]

    def _create_non_tempai_hand(self) -> list[int]:
        """
        Create a non-tempai hand (random disconnected tiles).
        """
        return [0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96]

    def _create_player_and_round_state(
        self,
        *,
        tiles: list[int] | None = None,
        score: int = 25000,
        melds: list | None = None,
        wall_size: int = 10,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Test",
            tiles=tiles or self._create_tempai_hand(),
            score=score,
            melds=melds or [],
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(wall_size)),
            players=players,
        )
        return player, round_state

    def test_can_declare_riichi_with_tempai_closed_hand(self):
        """Player can declare riichi with tempai and closed hand."""
        player, round_state = self._create_player_and_round_state()

        result = can_declare_riichi(player, round_state)

        assert result is True

    def test_cannot_declare_riichi_with_low_points(self):
        """Player cannot declare riichi with less than 1000 points."""
        player, round_state = self._create_player_and_round_state(score=999)

        result = can_declare_riichi(player, round_state)

        assert result is False

    def test_can_declare_riichi_with_exactly_1000_points(self):
        """Player can declare riichi with exactly 1000 points."""
        player, round_state = self._create_player_and_round_state(score=1000)

        result = can_declare_riichi(player, round_state)

        assert result is True

    def test_cannot_declare_riichi_with_open_meld(self):
        """Player cannot declare riichi with an open meld."""
        open_meld = Meld(meld_type=Meld.PON, tiles=[0, 1, 2], opened=True)
        # hand with open meld has fewer tiles (10 instead of 13)
        tempai_hand_with_meld = [4, 8, 12, 16, 20, 24, 28, 29, 30, 32]
        player, round_state = self._create_player_and_round_state(
            tiles=tempai_hand_with_meld,
            melds=[open_meld],
        )

        result = can_declare_riichi(player, round_state)

        assert result is False

    def test_can_declare_riichi_with_closed_kan(self):
        """Player can declare riichi with a closed kan (not an open meld)."""
        closed_kan = Meld(meld_type=Meld.KAN, tiles=[0, 1, 2, 3], opened=False)
        # hand with closed kan has fewer tiles (10 instead of 13)
        tempai_hand_with_kan = [4, 8, 12, 16, 20, 24, 28, 29, 30, 32]
        player, round_state = self._create_player_and_round_state(
            tiles=tempai_hand_with_kan,
            melds=[closed_kan],
        )

        result = can_declare_riichi(player, round_state)

        assert result is True

    def test_cannot_declare_riichi_without_tempai(self):
        """Player cannot declare riichi without being in tempai."""
        player, round_state = self._create_player_and_round_state(tiles=self._create_non_tempai_hand())

        result = can_declare_riichi(player, round_state)

        assert result is False

    def test_cannot_declare_riichi_with_empty_wall(self):
        """Player cannot declare riichi when wall is empty."""
        player, round_state = self._create_player_and_round_state(wall_size=0)

        result = can_declare_riichi(player, round_state)

        assert result is False

    def test_can_declare_riichi_with_one_tile_in_wall(self):
        """Player can declare riichi with at least one tile in wall."""
        player, round_state = self._create_player_and_round_state(wall_size=1)

        result = can_declare_riichi(player, round_state)

        assert result is True


class TestDeclareRiichi:
    def _create_tempai_hand(self) -> list[int]:
        """Create a tempai hand."""
        return [0, 1, 4, 8, 12, 16, 20, 24, 28, 29, 30, 32, 33]

    def _create_game_state(
        self,
        *,
        player_discards: list[Discard] | None = None,
        players_with_open_hands: list[int] | None = None,
        riichi_sticks: int = 0,
    ) -> tuple[MahjongPlayer, MahjongGameState]:
        """Create game state for testing riichi declaration."""
        player = MahjongPlayer(
            seat=0,
            name="Test",
            tiles=self._create_tempai_hand(),
            score=25000,
            discards=player_discards or [],
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(10)),
            players=players,
            players_with_open_hands=players_with_open_hands or [],
        )
        game_state = MahjongGameState(
            round_state=round_state,
            riichi_sticks=riichi_sticks,
        )
        return player, game_state

    def test_declare_riichi_sets_riichi_flag(self):
        """Declaring riichi sets the is_riichi flag."""
        player, game_state = self._create_game_state()
        assert player.is_riichi is False

        declare_riichi(player, game_state)

        assert player.is_riichi is True

    def test_declare_riichi_sets_ippatsu_flag(self):
        """Declaring riichi sets the ippatsu flag."""
        player, game_state = self._create_game_state()
        assert player.is_ippatsu is False

        declare_riichi(player, game_state)

        assert player.is_ippatsu is True

    def test_declare_riichi_deducts_1000_points(self):
        """Declaring riichi deducts 1000 points from player."""
        player, game_state = self._create_game_state()
        player.score = 25000

        declare_riichi(player, game_state)

        assert player.score == 24000

    def test_declare_riichi_increments_riichi_sticks(self):
        """Declaring riichi increments the riichi sticks count."""
        player, game_state = self._create_game_state(riichi_sticks=0)

        declare_riichi(player, game_state)

        assert game_state.riichi_sticks == 1

    def test_declare_riichi_multiple_sticks(self):
        """Multiple riichi declarations accumulate sticks."""
        player, game_state = self._create_game_state(riichi_sticks=2)

        declare_riichi(player, game_state)

        assert game_state.riichi_sticks == 3

    def test_declare_double_riichi_on_first_turn(self):
        """Declaring riichi on first turn with no open hands is double riichi.

        In the actual game flow, declare_riichi is called AFTER the riichi discard
        is added to player.discards. So for double riichi, len(discards) == 1.
        """
        player, game_state = self._create_game_state(
            player_discards=[Discard(tile_id=100, is_riichi_discard=True)],  # riichi discard already added
            players_with_open_hands=[],
        )
        assert player.is_daburi is False

        declare_riichi(player, game_state)

        assert player.is_daburi is True

    def test_no_double_riichi_after_first_discard(self):
        """No double riichi if player has already discarded before riichi.

        In the actual game flow, declare_riichi is called AFTER the riichi discard
        is added. So for non-double riichi, len(discards) > 1.
        """
        player, game_state = self._create_game_state(
            player_discards=[
                Discard(tile_id=100),  # previous discard
                Discard(tile_id=101, is_riichi_discard=True),  # riichi discard
            ],
            players_with_open_hands=[],
        )

        declare_riichi(player, game_state)

        assert player.is_daburi is False

    def test_no_double_riichi_if_open_hands_exist(self):
        """No double riichi if any player has called an open meld."""
        player, game_state = self._create_game_state(
            player_discards=[Discard(tile_id=100, is_riichi_discard=True)],  # riichi discard already added
            players_with_open_hands=[1],  # bot 1 has open hand
        )

        declare_riichi(player, game_state)

        assert player.is_daburi is False


class TestGetUraDora:
    def _create_round_state_with_dead_wall(self, dead_wall_size: int = 14) -> MahjongRoundState:
        """Create a round state with a dead wall for testing."""
        dead_wall = list(range(122, 122 + dead_wall_size))
        return MahjongRoundState(dead_wall=dead_wall)

    def test_get_ura_dora_returns_one_tile(self):
        """Get one ura dora tile when num_dora is 1."""
        round_state = self._create_round_state_with_dead_wall()

        result = get_ura_dora(round_state, num_dora=1)

        assert len(result) == 1
        assert result[0] == round_state.dead_wall[FIRST_URA_DORA_INDEX]

    def test_get_ura_dora_returns_two_tiles(self):
        """Get two ura dora tiles when num_dora is 2."""
        round_state = self._create_round_state_with_dead_wall()

        result = get_ura_dora(round_state, num_dora=2)

        assert len(result) == 2
        assert result[0] == round_state.dead_wall[FIRST_URA_DORA_INDEX]
        assert result[1] == round_state.dead_wall[FIRST_URA_DORA_INDEX + 1]

    def test_get_ura_dora_returns_four_tiles(self):
        """Get four ura dora tiles when num_dora is 4."""
        round_state = self._create_round_state_with_dead_wall()

        result = get_ura_dora(round_state, num_dora=4)

        assert len(result) == 4
        for i in range(4):
            assert result[i] == round_state.dead_wall[FIRST_URA_DORA_INDEX + i]

    def test_get_ura_dora_returns_empty_for_zero(self):
        """Get empty list when num_dora is 0."""
        round_state = self._create_round_state_with_dead_wall()

        result = get_ura_dora(round_state, num_dora=0)

        assert result == []

    def test_get_ura_dora_handles_small_dead_wall(self):
        """Handles cases where dead wall is smaller than expected."""
        # smaller dead wall that doesn't have all ura dora tiles
        round_state = self._create_round_state_with_dead_wall(dead_wall_size=10)

        result = get_ura_dora(round_state, num_dora=4)

        # should only return what's available
        assert len(result) == 1  # only index 9 is available
        assert result[0] == round_state.dead_wall[FIRST_URA_DORA_INDEX]

    def test_get_ura_dora_correct_positions(self):
        """Verify ura dora are at correct dead wall positions (9, 10, 11, 12)."""
        round_state = self._create_round_state_with_dead_wall()

        result = get_ura_dora(round_state, num_dora=4)

        # ura dora should be at indices 9, 10, 11, 12 in dead wall
        assert result[0] == round_state.dead_wall[9]
        assert result[1] == round_state.dead_wall[10]
        assert result[2] == round_state.dead_wall[11]
        assert result[3] == round_state.dead_wall[12]
