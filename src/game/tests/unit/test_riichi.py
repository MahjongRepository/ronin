"""
Unit tests for riichi declaration and related mechanics.
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.riichi import can_declare_riichi
from game.logic.settings import GameSettings
from game.logic.state import (
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.wall import Wall


class TestCanDeclareRiichi:
    def _create_tempai_hand(self) -> list[int]:
        """
        Create a tempai hand: 11m 234m 567m 888m 9m, waiting for 9m pair.
        """
        return TilesConverter.string_to_136_array(man="1123456788899")

    def _create_non_tempai_hand(self) -> list[int]:
        """
        Create a non-tempai hand (random disconnected tiles).
        """
        return TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357")

    def _create_player_and_round_state(
        self,
        *,
        tiles: list[int] | None = None,
        score: int = 25000,
        melds: tuple | None = None,
        wall_size: int = 10,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Test",
            tiles=tuple(tiles) if tiles else tuple(self._create_tempai_hand()),
            score=score,
            melds=melds or (),
        )
        players = (player, *(MahjongPlayer(seat=i, name=f"AI{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=Wall(live_tiles=tuple(range(wall_size))),
            players=players,
        )
        return player, round_state

    def test_can_declare_riichi_with_tempai_closed_hand(self):
        """Player can declare riichi with tempai and closed hand."""
        player, round_state = self._create_player_and_round_state()

        result = can_declare_riichi(player, round_state, GameSettings())

        assert result is True

    def test_cannot_declare_riichi_with_low_points(self):
        """Player cannot declare riichi with less than 1000 points."""
        player, round_state = self._create_player_and_round_state(score=999)

        result = can_declare_riichi(player, round_state, GameSettings())

        assert result is False

    def test_can_declare_riichi_with_exactly_1000_points(self):
        """Player can declare riichi with exactly 1000 points."""
        player, round_state = self._create_player_and_round_state(score=1000)

        result = can_declare_riichi(player, round_state, GameSettings())

        assert result is True

    def test_cannot_declare_riichi_with_open_meld(self):
        """Player cannot declare riichi with an open meld."""
        open_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
        )
        # hand with open meld has fewer tiles (10 instead of 13)
        tempai_hand_with_meld = TilesConverter.string_to_136_array(man="2345678889")
        player, round_state = self._create_player_and_round_state(
            tiles=tempai_hand_with_meld,
            melds=(open_meld,),
        )

        result = can_declare_riichi(player, round_state, GameSettings())

        assert result is False

    def test_can_declare_riichi_with_closed_kan(self):
        """Player can declare riichi with a closed kan (not an open meld)."""
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="1111")),
            opened=False,
        )
        # hand with closed kan has fewer tiles (10 instead of 13)
        tempai_hand_with_kan = TilesConverter.string_to_136_array(man="2345678889")
        player, round_state = self._create_player_and_round_state(
            tiles=tempai_hand_with_kan,
            melds=(closed_kan,),
        )

        result = can_declare_riichi(player, round_state, GameSettings())

        assert result is True

    def test_cannot_declare_riichi_without_tempai(self):
        """Player cannot declare riichi without being in tempai."""
        player, round_state = self._create_player_and_round_state(tiles=self._create_non_tempai_hand())

        result = can_declare_riichi(player, round_state, GameSettings())

        assert result is False

    def test_cannot_declare_riichi_with_empty_wall(self):
        """Player cannot declare riichi when wall is empty."""
        player, round_state = self._create_player_and_round_state(wall_size=0)

        result = can_declare_riichi(player, round_state, GameSettings())

        assert result is False

    def test_cannot_declare_riichi_with_fewer_than_4_tiles_in_wall(self):
        """Player cannot declare riichi when fewer than 4 tiles remain in wall."""
        player, round_state = self._create_player_and_round_state(wall_size=3)

        result = can_declare_riichi(player, round_state, GameSettings())

        assert result is False

    def test_can_declare_riichi_with_exactly_4_tiles_in_wall(self):
        """Player can declare riichi with exactly 4 tiles in wall."""
        player, round_state = self._create_player_and_round_state(wall_size=4)

        result = can_declare_riichi(player, round_state, GameSettings())

        assert result is True
