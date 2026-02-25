"""
Unit tests for AI player decision making.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.ai_player import AIPlayer, AIPlayerStrategy
from game.logic.enums import KanType
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.wall import Wall
from game.tests.unit.helpers import _string_to_34_tile


def _make_round_state(
    tiles: list[int],
) -> tuple[MahjongPlayer, MahjongRoundState]:
    """Create a player and round state for testing."""
    player = MahjongPlayer(
        seat=0,
        name="AI",
        tiles=tuple(tiles),
        score=25000,
    )
    players = (player, *(MahjongPlayer(seat=i, name=f"AI{i}", score=25000) for i in range(1, 4)))
    round_state = MahjongRoundState(
        wall=Wall(live_tiles=tuple(range(10))),
        players=players,
    )
    return player, round_state


class TestTsumogiriPassesOnAllCalls:
    """Tsumogiri AI declines every call opportunity."""

    def test_passes_on_pon(self):
        ai = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="1123456789", pin="123")
        player, rs = _make_round_state(tiles)
        discarded = TilesConverter.string_to_136_array(man="111")[2]

        assert ai.should_call_pon(player, discarded_tile=discarded, round_state=rs) is False

    def test_passes_on_chi(self):
        ai = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="12", pin="1", sou="1")
        player, rs = _make_round_state(tiles)
        man_12 = TilesConverter.string_to_136_array(man="12")

        assert (
            ai.should_call_chi(
                player,
                discarded_tile=TilesConverter.string_to_136_array(man="3")[0],
                chi_options=((man_12[0], man_12[1]),),
                round_state=rs,
            )
            is None
        )

    def test_passes_on_kan(self):
        ai = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="111", pin="1")
        player, rs = _make_round_state(tiles)

        result = ai.should_call_kan(
            player,
            kan_type=KanType.OPEN,
            tile_34=_string_to_34_tile(man="1"),
            round_state=rs,
        )
        assert result is False

    def test_passes_on_ron(self):
        ai = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1", sou="123")
        player, rs = _make_round_state(tiles)
        discarded = TilesConverter.string_to_136_array(pin="11")[1]

        assert ai.should_call_ron(player, discarded_tile=discarded, round_state=rs) is False


class TestSelectDiscard:
    def test_discards_last_tile(self):
        """Tsumogiri always discards the most recently drawn tile."""
        ai = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12345")
        player, rs = _make_round_state(tiles)

        assert ai.select_discard(player, rs) == tiles[-1]

    def test_empty_hand_raises_value_error(self):
        ai = AIPlayer()
        player = MahjongPlayer(seat=0, name="AI", tiles=(), score=25000)
        players = (player, *(MahjongPlayer(seat=i, name=f"AI{i}", score=25000) for i in range(1, 4)))
        rs = MahjongRoundState(wall=Wall(live_tiles=tuple(range(10))), players=players)

        with pytest.raises(ValueError, match="cannot select discard from empty hand"):
            ai.select_discard(player, rs)
