"""
Unit tests for bot decision making.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.bot import (
    BotPlayer,
    BotStrategy,
    get_bot_action,
    select_discard,
    should_call_chi,
    should_call_kan,
    should_call_pon,
    should_call_ron,
)
from game.logic.enums import KanType, PlayerAction
from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.tests.unit.helpers import _string_to_34_tile


class TestBotPlayer:
    def test_create_bot_with_default_strategy(self):
        """BotPlayer defaults to TSUMOGIRI strategy."""
        bot = BotPlayer()

        assert bot.strategy == BotStrategy.TSUMOGIRI

    def test_create_bot_with_explicit_strategy(self):
        """BotPlayer can be created with explicit strategy."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)

        assert bot.strategy == BotStrategy.TSUMOGIRI


class TestShouldCallPon:
    def _create_player_and_round_state(
        self,
        tiles: list[int],
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            tiles=tuple(tiles),
            score=25000,
        )
        players = (player, *(MahjongPlayer(seat=i, name=f"Bot{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=tuple(range(10)),
            players=players,
        )
        return player, round_state

    def test_always_passes_on_pon(self):
        """Tsumogiri bot always passes on pon."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="1123456789", pin="123")
        player, round_state = self._create_player_and_round_state(tiles)

        discarded_tile = TilesConverter.string_to_136_array(man="111")[2]
        result = should_call_pon(bot, player, discarded_tile=discarded_tile, round_state=round_state)

        assert result is False


class TestShouldCallChi:
    def _create_player_and_round_state(
        self,
        tiles: list[int],
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            tiles=tuple(tiles),
            score=25000,
        )
        players = (player, *(MahjongPlayer(seat=i, name=f"Bot{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=tuple(range(10)),
            players=players,
        )
        return player, round_state

    def test_always_passes_on_chi(self):
        """Tsumogiri bot always passes on chi."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="12", pin="1", sou="1")
        player, round_state = self._create_player_and_round_state(tiles)
        man_12 = TilesConverter.string_to_136_array(man="12")
        chi_options = [(man_12[0], man_12[1])]

        discarded_tile = TilesConverter.string_to_136_array(man="3")[0]
        result = should_call_chi(
            bot, player, discarded_tile=discarded_tile, chi_options=chi_options, round_state=round_state
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
            name="Bot",
            tiles=tuple(tiles),
            melds=melds or (),
            score=25000,
        )
        players = (player, *(MahjongPlayer(seat=i, name=f"Bot{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=tuple(range(10)),
            players=players,
        )
        return player, round_state

    def test_always_passes_on_open_kan(self):
        """Tsumogiri bot always passes on open kan."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="111", pin="1")
        player, round_state = self._create_player_and_round_state(tiles)

        result = should_call_kan(
            bot, player, kan_type=KanType.OPEN, tile_34=_string_to_34_tile(man="1"), round_state=round_state
        )

        assert result is False

    def test_always_passes_on_closed_kan(self):
        """Tsumogiri bot always passes on closed kan."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="1111", pin="1")
        player, round_state = self._create_player_and_round_state(tiles)

        result = should_call_kan(
            bot, player, kan_type=KanType.CLOSED, tile_34=_string_to_34_tile(man="1"), round_state=round_state
        )

        assert result is False

    def test_always_passes_on_added_kan(self):
        """Tsumogiri bot always passes on added kan."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon = FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(man_1m[:3]), opened=True)
        hand = [man_1m[3], *TilesConverter.string_to_136_array(pin="1", sou="1")]
        player, round_state = self._create_player_and_round_state(hand, melds=(pon,))

        result = should_call_kan(
            bot, player, kan_type=KanType.ADDED, tile_34=_string_to_34_tile(man="1"), round_state=round_state
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
            name="Bot",
            tiles=tuple(tiles),
            score=25000,
        )
        players = (player, *(MahjongPlayer(seat=i, name=f"Bot{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=tuple(range(10)),
            players=players,
        )
        return player, round_state

    def test_always_passes_on_ron(self):
        """Tsumogiri bot always passes on ron."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1", sou="123")
        player, round_state = self._create_player_and_round_state(tiles)

        discarded_tile = TilesConverter.string_to_136_array(pin="11")[1]
        result = should_call_ron(bot, player, discarded_tile=discarded_tile, round_state=round_state)

        assert result is False


class TestSelectDiscard:
    def _create_player_and_round_state(
        self,
        tiles: list[int],
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            tiles=tuple(tiles),
            score=25000,
        )
        players = (player, *(MahjongPlayer(seat=i, name=f"Bot{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=tuple(range(10)),
            players=players,
        )
        return player, round_state

    def test_discards_last_tile(self):
        """Tsumogiri bot discards the last tile (most recently drawn)."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12345")
        player, round_state = self._create_player_and_round_state(tiles)

        result = select_discard(bot, player, round_state)

        assert result == tiles[-1]

    def test_always_discards_last_tile(self):
        """Tsumogiri bot consistently discards the most recent tile."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="1111222233334", sou="8")
        player, round_state = self._create_player_and_round_state(tiles)

        result = select_discard(bot, player, round_state)

        assert result == tiles[-1]

    def test_empty_hand_raises_value_error(self):
        """select_discard raises ValueError on empty hand."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player = MahjongPlayer(seat=0, name="Bot", tiles=(), score=25000)
        players = (player, *(MahjongPlayer(seat=i, name=f"Bot{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(wall=tuple(range(10)), players=players)

        with pytest.raises(ValueError, match="cannot select discard from empty hand"):
            select_discard(bot, player, round_state)


class TestGetBotAction:
    def _create_player_and_round_state(
        self,
        tiles: list[int],
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            tiles=tuple(tiles),
            score=25000,
        )
        players = (player, *(MahjongPlayer(seat=i, name=f"Bot{i}", score=25000) for i in range(1, 4)))
        round_state = MahjongRoundState(
            wall=tuple(range(10)),
            players=players,
        )
        return player, round_state

    def test_always_returns_discard_action(self):
        """Bot always returns a discard action with the last tile."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="13579")
        player, round_state = self._create_player_and_round_state(tiles)

        result = get_bot_action(bot, player, round_state)

        assert result.action == PlayerAction.DISCARD
        assert result.tile_id == tiles[-1]

    def test_discards_last_tile_from_winning_hand(self):
        """Bot discards even when holding a winning hand."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="11", sou="123")
        player, round_state = self._create_player_and_round_state(tiles)

        result = get_bot_action(bot, player, round_state)

        assert result.action == PlayerAction.DISCARD
        assert result.tile_id == tiles[-1]

    def test_discards_last_tile_from_tempai_hand(self):
        """Bot discards even when in tempai (no riichi declaration)."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="111", honors="12")
        player, round_state = self._create_player_and_round_state(tiles)

        result = get_bot_action(bot, player, round_state)

        assert result.action == PlayerAction.DISCARD
        assert result.tile_id == tiles[-1]
