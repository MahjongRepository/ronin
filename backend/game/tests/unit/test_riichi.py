from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.riichi import can_declare_riichi
from game.logic.settings import GameSettings
from game.logic.state import (
    MahjongPlayer,
    MahjongRoundState,
)
from game.tests.helpers.wall import make_wall


class TestCanDeclareRiichi:
    def _create_tempai_hand(self) -> list[int]:
        return TilesConverter.string_to_136_array(man="1123456788899")

    def _create_non_tempai_hand(self) -> list[int]:
        return TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357")

    def _create_player_and_round_state(
        self,
        *,
        tiles: list[int] | None = None,
        score: int = 25000,
        melds: tuple | None = None,
        wall_size: int = 10,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        player = MahjongPlayer(
            seat=0,
            name="Test",
            tiles=tuple(tiles) if tiles else tuple(self._create_tempai_hand()),
            score=score,
            melds=melds or (),
        )
        players = (player, *(MahjongPlayer(seat=i, name=f"AI{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=make_wall(live_tiles=tuple(range(wall_size))),
            players=players,
        )
        return player, round_state

    def test_can_declare_riichi__when_closed_hand_tempai__should_allow(self):
        player, round_state = self._create_player_and_round_state()

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is True

    def test_can_declare_riichi__when_score_999__should_reject(self):
        player, round_state = self._create_player_and_round_state(score=999)

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is False

    def test_can_declare_riichi__when_score_exactly_1000__should_allow(self):
        player, round_state = self._create_player_and_round_state(score=1000)

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is True

    def test_can_declare_riichi__when_hand_has_open_meld__should_reject(self):
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

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is False

    def test_can_declare_riichi__when_hand_has_closed_kan__should_allow(self):
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

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is True

    def test_can_declare_riichi__when_not_tempai__should_reject(self):
        player, round_state = self._create_player_and_round_state(tiles=self._create_non_tempai_hand())

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is False

    def test_can_declare_riichi__when_wall_has_3_tiles__should_reject(self):
        player, round_state = self._create_player_and_round_state(wall_size=3)

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is False

    def test_can_declare_riichi__when_wall_has_4_tiles__should_allow(self):
        player, round_state = self._create_player_and_round_state(wall_size=4)

        result = can_declare_riichi(player, round_state, settings=GameSettings())
        assert result is True
