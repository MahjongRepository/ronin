"""
Unit tests for bot decision making.
"""

from mahjong.meld import Meld

from game.logic.bot import (
    BotPlayer,
    BotStrategy,
    get_bot_action,
    select_discard,
    select_riichi_discard,
    should_call_chi,
    should_call_kan,
    should_call_pon,
    should_call_riichi,
    should_call_ron,
    should_declare_tsumo,
)
from game.logic.state import Discard, MahjongPlayer, MahjongRoundState


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
        *,
        is_riichi: bool = False,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            is_bot=True,
            tiles=tiles,
            is_riichi=is_riichi,
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(10)),
            players=players,
        )
        return player, round_state

    def test_simple_bot_never_calls_pon(self):
        """Tsumogiri bot never calls pon to keep hand closed."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # player has 1m 1m in hand (tiles 0 and 1)
        player, round_state = self._create_player_and_round_state([0, 1, 36, 72])

        result = should_call_pon(bot, player, discarded_tile=2, round_state=round_state)

        assert result is False

    def test_simple_bot_refuses_pon_even_with_valid_opportunity(self):
        """Tsumogiri bot refuses pon even when it's a valid call."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # player has two matching tiles for a pon
        player, round_state = self._create_player_and_round_state(
            [0, 1, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44]
        )

        result = should_call_pon(bot, player, discarded_tile=2, round_state=round_state)

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
            is_bot=True,
            tiles=tiles,
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(10)),
            players=players,
        )
        return player, round_state

    def test_simple_bot_never_calls_chi(self):
        """Tsumogiri bot never calls chi to keep hand closed."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # player has 1m 2m (tiles 0 and 4)
        player, round_state = self._create_player_and_round_state([0, 4, 36, 72])
        # chi options would be for 3m (completing 123m sequence)
        chi_options = [(0, 4)]  # the two tiles from hand to use

        result = should_call_chi(
            bot, player, discarded_tile=8, chi_options=chi_options, round_state=round_state
        )

        assert result is None

    def test_simple_bot_refuses_chi_with_empty_options(self):
        """Tsumogiri bot returns None when no chi options available."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state([0, 36, 72, 108])

        result = should_call_chi(bot, player, discarded_tile=8, chi_options=[], round_state=round_state)

        assert result is None


class TestShouldCallKan:
    def _create_player_and_round_state(
        self,
        tiles: list[int],
        *,
        melds: list | None = None,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            is_bot=True,
            tiles=tiles,
            melds=melds or [],
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(10)),
            players=players,
        )
        return player, round_state

    def test_simple_bot_never_calls_open_kan(self):
        """Tsumogiri bot never calls open kan."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # player has 1m 1m 1m in hand
        player, round_state = self._create_player_and_round_state([0, 1, 2, 36])

        result = should_call_kan(bot, player, kan_type="open", tile_34=0, round_state=round_state)

        assert result is False

    def test_simple_bot_never_calls_closed_kan(self):
        """Tsumogiri bot never calls closed kan."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # player has all four 1m tiles
        player, round_state = self._create_player_and_round_state([0, 1, 2, 3, 36])

        result = should_call_kan(bot, player, kan_type="closed", tile_34=0, round_state=round_state)

        assert result is False

    def test_simple_bot_never_calls_added_kan(self):
        """Tsumogiri bot never calls added kan."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # player has a pon and the 4th tile
        pon = Meld(meld_type=Meld.PON, tiles=[0, 1, 2], opened=True)
        player, round_state = self._create_player_and_round_state([3, 36, 72], melds=[pon])

        result = should_call_kan(bot, player, kan_type="added", tile_34=0, round_state=round_state)

        assert result is False


class TestShouldCallRon:
    def _create_winning_hand(self) -> list[int]:
        """
        Create a complete winning hand: 123m 456m 789m 11p 234s.
        """
        return [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,  # 11p (pair)
            72,
            76,
            80,  # 234s
        ]

    def _create_tempai_hand(self) -> list[int]:
        """
        Create a tempai hand: 123m 456m 789m 1p 234s, waiting for 1p pair.
        """
        return [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,  # 1p (single, waiting for pair)
            72,
            76,
            80,  # 234s
        ]

    def _create_player_and_round_state(
        self,
        tiles: list[int],
        *,
        discards: list[Discard] | None = None,
        is_riichi: bool = False,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            is_bot=True,
            tiles=tiles,
            discards=discards or [],
            is_riichi=is_riichi,
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(10)),
            players=players,
            dealer_seat=0,
            round_wind=0,
        )
        return player, round_state

    def test_simple_bot_calls_ron_when_able(self):
        """Tsumogiri bot always calls ron when it can win."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # tempai hand waiting for 1p to complete pair
        player, round_state = self._create_player_and_round_state(
            self._create_tempai_hand(),
            is_riichi=True,  # riichi provides yaku
        )

        # discard is 1p (tile 37 - same type as the 36 in hand)
        result = should_call_ron(bot, player, discarded_tile=37, round_state=round_state)

        assert result is True

    def test_simple_bot_does_not_call_ron_when_furiten(self):
        """Tsumogiri bot does not call ron when in furiten."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # tempai hand, but player has discarded their wait tile
        player, round_state = self._create_player_and_round_state(
            self._create_tempai_hand(),
            discards=[Discard(tile_id=37)],  # discarded 1p, now furiten
            is_riichi=True,
        )

        result = should_call_ron(bot, player, discarded_tile=38, round_state=round_state)

        assert result is False

    def test_simple_bot_does_not_call_ron_when_hand_not_complete(self):
        """Tsumogiri bot does not call ron when discarded tile doesn't complete hand."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(
            self._create_tempai_hand(),
            is_riichi=True,
        )

        # wrong tile - 2p instead of 1p
        result = should_call_ron(bot, player, discarded_tile=40, round_state=round_state)

        assert result is False


class TestShouldCallRiichi:
    def _create_tempai_hand(self) -> list[int]:
        """Create a tempai hand: 11m 234m 567m 888m 9m, waiting for 9m pair."""
        return [0, 1, 4, 8, 12, 16, 20, 24, 28, 29, 30, 32, 33]

    def _create_non_tempai_hand(self) -> list[int]:
        """Create a non-tempai hand."""
        return [0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96]

    def _create_player_and_round_state(
        self,
        tiles: list[int],
        *,
        score: int = 25000,
        melds: list | None = None,
        wall_size: int = 10,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            is_bot=True,
            tiles=tiles,
            score=score,
            melds=melds or [],
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(wall_size)),
            players=players,
        )
        return player, round_state

    def test_simple_bot_calls_riichi_when_tempai(self):
        """Tsumogiri bot always calls riichi when in tempai with closed hand."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(self._create_tempai_hand())

        result = should_call_riichi(bot, player, round_state)

        assert result is True

    def test_simple_bot_does_not_call_riichi_without_tempai(self):
        """Tsumogiri bot does not call riichi without tempai."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(self._create_non_tempai_hand())

        result = should_call_riichi(bot, player, round_state)

        assert result is False

    def test_simple_bot_does_not_call_riichi_with_low_points(self):
        """Tsumogiri bot does not call riichi with less than 1000 points."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(
            self._create_tempai_hand(),
            score=999,
        )

        result = should_call_riichi(bot, player, round_state)

        assert result is False

    def test_simple_bot_does_not_call_riichi_with_open_meld(self):
        """Tsumogiri bot does not call riichi with open meld."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        open_meld = Meld(meld_type=Meld.PON, tiles=[0, 1, 2], opened=True)
        # adjust hand for open meld
        player, round_state = self._create_player_and_round_state(
            [4, 8, 12, 16, 20, 24, 28, 29, 30, 32],
            melds=[open_meld],
        )

        result = should_call_riichi(bot, player, round_state)

        assert result is False


class TestShouldDeclareTsumo:
    def _create_winning_hand(self) -> list[int]:
        """
        Create a complete winning hand: 123m 456m 789m 11p 234s.
        """
        return [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,  # 11p (pair)
            72,
            76,
            80,  # 234s
        ]

    def _create_non_winning_hand(self) -> list[int]:
        """Create a non-winning hand."""
        return [0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 100]

    def _create_player_and_round_state(
        self,
        tiles: list[int],
        *,
        is_riichi: bool = False,
        melds: list | None = None,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            is_bot=True,
            tiles=tiles,
            is_riichi=is_riichi,
            melds=melds or [],
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(10)),
            players=players,
            dealer_seat=0,
            round_wind=0,
        )
        return player, round_state

    def test_simple_bot_declares_tsumo_when_winning(self):
        """Tsumogiri bot always declares tsumo when holding a winning hand."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(
            self._create_winning_hand(),
            is_riichi=True,  # riichi provides yaku
        )

        result = should_declare_tsumo(bot, player, round_state)

        assert result is True

    def test_simple_bot_does_not_declare_tsumo_without_winning_hand(self):
        """Tsumogiri bot does not declare tsumo without winning hand."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(self._create_non_winning_hand())

        result = should_declare_tsumo(bot, player, round_state)

        assert result is False

    def test_simple_bot_declares_tsumo_with_closed_hand(self):
        """Tsumogiri bot declares tsumo with closed hand (menzen tsumo yaku)."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # closed winning hand - menzen tsumo is always a valid yaku
        player, round_state = self._create_player_and_round_state(self._create_winning_hand())

        result = should_declare_tsumo(bot, player, round_state)

        assert result is True


class TestSelectDiscard:
    def _create_player_and_round_state(
        self,
        tiles: list[int],
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            is_bot=True,
            tiles=tiles,
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(10)),
            players=players,
        )
        return player, round_state

    def test_simple_bot_discards_last_tile_tsumogiri(self):
        """Tsumogiri bot discards the last tile (tsumogiri strategy)."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # hand with last tile being 44 (recently drawn)
        tiles = [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52]
        player, round_state = self._create_player_and_round_state(tiles)

        result = select_discard(bot, player, round_state)

        assert result == 52  # last tile

    def test_simple_bot_always_discards_last_tile(self):
        """Tsumogiri bot consistently discards the most recent tile."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        tiles = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 100]
        player, round_state = self._create_player_and_round_state(tiles)

        result = select_discard(bot, player, round_state)

        assert result == 100


class TestSelectRiichiDiscard:
    def _create_tempai_hand_with_isolated_extra(self) -> list[int]:
        """
        Create a 14-tile tempai hand with isolated honor tiles as extras.

        Hand: 123m 456m 789m 111p + E + S (extra)
        Only E (108) and S (112) keep tempai when discarded.
        """
        return [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,
            38,  # 111p (triplet)
            108,  # E (East)
            112,  # S (South - last tile, extra)
        ]

    def _create_player(self, tiles: list[int]) -> MahjongPlayer:
        """Create a player for testing."""
        return MahjongPlayer(
            seat=0,
            name="Bot",
            is_bot=True,
            tiles=tiles,
        )

    def test_select_riichi_discard_returns_tile_keeping_tempai(self):
        """Riichi discard keeps hand in tempai."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player = self._create_player(self._create_tempai_hand_with_isolated_extra())

        result = select_riichi_discard(bot, player)

        # should return the last tile (112 South) since it keeps tempai
        assert result == 112

    def test_select_riichi_discard_prefers_last_tile_if_valid(self):
        """Riichi discard prefers tsumogiri if it maintains tempai."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        # tempai hand where last tile (South) keeps tempai
        tiles = [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,
            38,  # 111p (triplet)
            108,  # E (East)
            112,  # S (South - last tile, extra)
        ]
        player = self._create_player(tiles)

        result = select_riichi_discard(bot, player)

        # should prefer the last tile (112) since it keeps tempai
        assert result == 112


class TestGetBotAction:
    def _create_winning_hand(self) -> list[int]:
        """Create a complete winning hand: 123m 456m 789m 11p 234s."""
        return [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,  # 11p (pair)
            72,
            76,
            80,  # 234s
        ]

    def _create_tempai_hand(self) -> list[int]:
        """
        Create a 14-tile tempai hand with extra honor tile.

        Hand: 123m 456m 789m 111p + E + S (extra)
        Discarding E or S keeps tempai.
        """
        return [
            0,
            4,
            8,  # 123m
            12,
            16,
            20,  # 456m
            24,
            28,
            32,  # 789m
            36,
            37,
            38,  # 111p (triplet)
            108,  # E (East)
            112,  # S (South - extra)
        ]

    def _create_non_tempai_hand(self) -> list[int]:
        """Create a non-tempai hand."""
        return [0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104]

    def _create_player_and_round_state(
        self,
        tiles: list[int],
        *,
        is_riichi: bool = False,
        score: int = 25000,
    ) -> tuple[MahjongPlayer, MahjongRoundState]:
        """Create a player and round state for testing."""
        player = MahjongPlayer(
            seat=0,
            name="Bot",
            is_bot=True,
            tiles=tiles,
            is_riichi=is_riichi,
            score=score,
        )
        players = [player] + [MahjongPlayer(seat=i, name=f"Bot{i}", is_bot=True) for i in range(1, 4)]
        round_state = MahjongRoundState(
            wall=list(range(10)),
            players=players,
            dealer_seat=0,
            round_wind=0,
        )
        return player, round_state

    def test_bot_action_tsumo_when_winning(self):
        """Bot declares tsumo when holding a winning hand."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(self._create_winning_hand())

        result = get_bot_action(bot, player, round_state)

        assert result.action == "tsumo"
        assert result.tile_id is None

    def test_bot_action_riichi_when_tempai(self):
        """Bot declares riichi when in tempai with closed hand."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(self._create_tempai_hand())

        result = get_bot_action(bot, player, round_state)

        assert result.action == "riichi"
        assert result.tile_id is not None

    def test_bot_action_discard_when_not_tempai(self):
        """Bot discards when not in tempai."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(self._create_non_tempai_hand())

        result = get_bot_action(bot, player, round_state)

        assert result.action == "discard"
        assert result.tile_id is not None

    def test_bot_action_discard_when_already_riichi(self):
        """Bot only discards when already in riichi (can't riichi again)."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(
            self._create_tempai_hand(),
            is_riichi=True,
        )

        result = get_bot_action(bot, player, round_state)

        # already in riichi, so just discard
        assert result.action == "discard"

    def test_bot_action_discard_when_not_enough_points_for_riichi(self):
        """Bot discards instead of riichi when score is below 1000."""
        bot = BotPlayer(strategy=BotStrategy.TSUMOGIRI)
        player, round_state = self._create_player_and_round_state(
            self._create_tempai_hand(),
            score=500,
        )

        result = get_bot_action(bot, player, round_state)

        assert result.action == "discard"
