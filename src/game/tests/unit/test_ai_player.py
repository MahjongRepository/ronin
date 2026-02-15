"""
Unit tests for AI player decision making.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.ai_player import (
    AIPlayer,
    AIPlayerStrategy,
    get_ai_player_action,
    select_discard,
    should_call_chi,
    should_call_kan,
    should_call_pon,
    should_call_ron,
)
from game.logic.enums import KanType, PlayerAction
from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.wall import Wall
from game.tests.unit.helpers import _string_to_34_tile


class TestAIPlayer:
    def test_create_ai_player_with_default_strategy(self):
        """AIPlayer defaults to TSUMOGIRI strategy."""
        ai_player = AIPlayer()

        assert ai_player.strategy == AIPlayerStrategy.TSUMOGIRI

    def test_create_ai_player_with_explicit_strategy(self):
        """AIPlayer can be created with explicit strategy."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)

        assert ai_player.strategy == AIPlayerStrategy.TSUMOGIRI


class TestShouldCallPon:
    def _create_player_and_round_state(
        self,
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

    def test_always_passes_on_pon(self):
        """Tsumogiri AI player always passes on pon."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="1123456789", pin="123")
        player, round_state = self._create_player_and_round_state(tiles)

        discarded_tile = TilesConverter.string_to_136_array(man="111")[2]
        result = should_call_pon(ai_player, player, discarded_tile=discarded_tile, round_state=round_state)

        assert result is False


class TestShouldCallChi:
    def _create_player_and_round_state(
        self,
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

    def test_always_passes_on_chi(self):
        """Tsumogiri AI player always passes on chi."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="12", pin="1", sou="1")
        player, round_state = self._create_player_and_round_state(tiles)
        man_12 = TilesConverter.string_to_136_array(man="12")
        chi_options = [(man_12[0], man_12[1])]

        discarded_tile = TilesConverter.string_to_136_array(man="3")[0]
        result = should_call_chi(
            ai_player, player, discarded_tile=discarded_tile, chi_options=chi_options, round_state=round_state
        )

        assert result is None


class TestShouldCallKan:
    def _create_player_and_round_state(
        self,
        tiles: list[int],
        *,
        melds: tuple | None = None,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="AI",
            tiles=tuple(tiles),
            melds=melds or (),
            score=25000,
        )
        players = (player, *(MahjongPlayer(seat=i, name=f"AI{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=Wall(live_tiles=tuple(range(10))),
            players=players,
        )
        return player, round_state

    def test_always_passes_on_open_kan(self):
        """Tsumogiri AI player always passes on open kan."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="111", pin="1")
        player, round_state = self._create_player_and_round_state(tiles)

        result = should_call_kan(
            ai_player,
            player,
            kan_type=KanType.OPEN,
            tile_34=_string_to_34_tile(man="1"),
            round_state=round_state,
        )

        assert result is False

    def test_always_passes_on_closed_kan(self):
        """Tsumogiri AI player always passes on closed kan."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="1111", pin="1")
        player, round_state = self._create_player_and_round_state(tiles)

        result = should_call_kan(
            ai_player,
            player,
            kan_type=KanType.CLOSED,
            tile_34=_string_to_34_tile(man="1"),
            round_state=round_state,
        )

        assert result is False

    def test_always_passes_on_added_kan(self):
        """Tsumogiri AI player always passes on added kan."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon = FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(man_1m[:3]), opened=True)
        hand = [man_1m[3], *TilesConverter.string_to_136_array(pin="1", sou="1")]
        player, round_state = self._create_player_and_round_state(hand, melds=(pon,))

        result = should_call_kan(
            ai_player,
            player,
            kan_type=KanType.ADDED,
            tile_34=_string_to_34_tile(man="1"),
            round_state=round_state,
        )

        assert result is False


class TestShouldCallRon:
    def _create_player_and_round_state(
        self,
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

    def test_always_passes_on_ron(self):
        """Tsumogiri AI player always passes on ron."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1", sou="123")
        player, round_state = self._create_player_and_round_state(tiles)

        discarded_tile = TilesConverter.string_to_136_array(pin="11")[1]
        result = should_call_ron(ai_player, player, discarded_tile=discarded_tile, round_state=round_state)

        assert result is False


class TestSelectDiscard:
    def _create_player_and_round_state(
        self,
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

    def test_discards_last_tile(self):
        """Tsumogiri AI player discards the last tile (most recently drawn)."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12345")
        player, round_state = self._create_player_and_round_state(tiles)

        result = select_discard(ai_player, player, round_state)

        assert result == tiles[-1]

    def test_always_discards_last_tile(self):
        """Tsumogiri AI player consistently discards the most recent tile."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="1111222233334", sou="8")
        player, round_state = self._create_player_and_round_state(tiles)

        result = select_discard(ai_player, player, round_state)

        assert result == tiles[-1]

    def test_empty_hand_raises_value_error(self):
        """select_discard raises ValueError on empty hand."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        player = MahjongPlayer(seat=0, name="AI", tiles=(), score=25000)
        players = (player, *(MahjongPlayer(seat=i, name=f"AI{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(wall=Wall(live_tiles=tuple(range(10))), players=players)
        with pytest.raises(ValueError, match="cannot select discard from empty hand"):
            select_discard(ai_player, player, round_state)


class TestGetAIPlayerAction:
    def _create_player_and_round_state(
        self,
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

    def test_always_returns_discard_action(self):
        """AI player always returns a discard action with the last tile."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="13579")
        player, round_state = self._create_player_and_round_state(tiles)

        result = get_ai_player_action(ai_player, player, round_state)

        assert result.action == PlayerAction.DISCARD
        assert result.tile_id == tiles[-1]

    def test_discards_last_tile_from_winning_hand(self):
        """AI player discards even when holding a winning hand."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="11", sou="123")
        player, round_state = self._create_player_and_round_state(tiles)

        result = get_ai_player_action(ai_player, player, round_state)

        assert result.action == PlayerAction.DISCARD
        assert result.tile_id == tiles[-1]

    def test_discards_last_tile_from_tempai_hand(self):
        """AI player discards even when in tempai (no riichi declaration)."""
        ai_player = AIPlayer(strategy=AIPlayerStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="111", honors="12")
        player, round_state = self._create_player_and_round_state(tiles)

        result = get_ai_player_action(ai_player, player, round_state)

        assert result.action == PlayerAction.DISCARD
        assert result.tile_id == tiles[-1]
