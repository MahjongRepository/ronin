"""
Unit tests for abortive draw conditions.
"""

from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.abortive import (
    KYUUSHU_MIN_TYPES,
    AbortiveDrawType,
    _count_terminal_honor_types,
    call_kyuushu_kyuuhai,
    can_call_kyuushu_kyuuhai,
    check_four_kans,
    check_four_riichi,
    check_four_winds,
    check_triple_ron,
    process_abortive_draw,
)
from game.logic.state import Discard, MahjongGameState, MahjongPlayer, MahjongRoundState


class TestCanCallKyuushuKyuuhai:
    def _create_round_state(self, tiles: list[int]) -> MahjongRoundState:
        """Create a round state with a player holding specific tiles."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=tiles),
            MahjongPlayer(seat=1, name="Bot1", tiles=[]),
            MahjongPlayer(seat=2, name="Bot2", tiles=[]),
            MahjongPlayer(seat=3, name="Bot3", tiles=[]),
        ]
        return MahjongRoundState(
            players=players,
            current_player_seat=0,
        )

    def _create_kyuushu_hand(self) -> list[int]:
        """
        Create a hand with exactly 9 different terminal/honor types.

        Terminal/honor tiles in 34-format:
        - 1m (0), 9m (8), 1p (9), 9p (17), 1s (18), 9s (26)
        - E (27), S (28), W (29), N (30), Haku (31), Hatsu (32), Chun (33)

        In 136-format, multiply by 4:
        - 1m: 0-3, 9m: 32-35, 1p: 36-39, 9p: 68-71, 1s: 72-75, 9s: 104-107
        - E: 108-111, S: 112-115, W: 116-119, N: 120-123
        - Haku: 124-127, Hatsu: 128-131, Chun: 132-135
        """
        # 9 different types: 1m, 9m, 1p, 9p, 1s, 9s, E, S, W + 5 middle tiles
        # 14 tiles (just drew)
        return [
            *TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123"),
            # filler tiles (middle tiles, not terminal/honor)
            *TilesConverter.string_to_136_array(man="22334"),
        ]

    def _create_non_kyuushu_hand(self) -> list[int]:
        """
        Create a hand with only 8 different terminal/honor types (not enough).
        """
        # 8 different types: 1m, 9m, 1p, 9p, 1s, 9s, E, S + 6 middle tiles
        return [
            *TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="12"),
            # filler tiles (middle tiles, not terminal/honor)
            *TilesConverter.string_to_136_array(man="223345"),
        ]

    def test_can_call_with_9_terminal_honor_types(self):
        """Player can call with exactly 9 terminal/honor types."""
        tiles = self._create_kyuushu_hand()
        round_state = self._create_round_state(tiles)

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state)

        assert result is True

    def test_cannot_call_with_8_terminal_honor_types(self):
        """Player cannot call with only 8 terminal/honor types."""
        tiles = self._create_non_kyuushu_hand()
        round_state = self._create_round_state(tiles)

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state)

        assert result is False

    def test_can_call_with_all_13_terminal_honor_types(self):
        """Player can call with all 13 terminal/honor types (kokushi-like hand)."""
        # all 13 terminal/honor types + 1 duplicate
        tiles = [
            *TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="1234567"),
            TilesConverter.string_to_136_array(man="11")[1],  # 1m (duplicate)
        ]
        round_state = self._create_round_state(tiles)

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state)

        assert result is True

    def test_cannot_call_if_discards_exist(self):
        """Player cannot call if any discards have been made."""
        tiles = self._create_kyuushu_hand()
        round_state = self._create_round_state(tiles)
        # add a discard to player 1
        round_state.players[1].discards.append(
            Discard(tile_id=TilesConverter.string_to_136_array(pin="444")[2])
        )

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state)

        assert result is False

    def test_cannot_call_if_player_discarded(self):
        """Player cannot call if they have already discarded."""
        tiles = self._create_kyuushu_hand()
        round_state = self._create_round_state(tiles)
        # add a discard to the calling player
        round_state.players[0].discards.append(
            Discard(tile_id=TilesConverter.string_to_136_array(pin="444")[2])
        )

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state)

        assert result is False

    def test_cannot_call_if_melds_exist(self):
        """Player cannot call if any melds have been made."""
        tiles = self._create_kyuushu_hand()
        round_state = self._create_round_state(tiles)
        # mark that player 2 has an open hand
        round_state.players_with_open_hands.append(2)

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state)

        assert result is False

    def test_counts_duplicates_as_single_type(self):
        """Multiple copies of same terminal/honor count as one type."""
        # 9 types but with duplicates: 1m 1m 1m 9m 1p 9p 1s 9s E S W (8 unique types)
        tiles = [
            *TilesConverter.string_to_136_array(man="111")[0:3],  # 1m x3
            *TilesConverter.string_to_136_array(man="9", pin="19", sou="19", honors="12"),
            # filler middle tiles
            *TilesConverter.string_to_136_array(man="2233"),
        ]
        round_state = self._create_round_state(tiles)

        result = can_call_kyuushu_kyuuhai(round_state.players[0], round_state)

        # only 8 unique types, not enough
        assert result is False


class TestCountTerminalHonorTypes:
    def test_counts_terminals_correctly(self):
        """Correctly counts terminal tiles (1 and 9 of each suit)."""
        # 1m, 9m, 1p, 9p, 1s, 9s
        tiles = TilesConverter.string_to_136_array(man="19", pin="19", sou="19")

        result = _count_terminal_honor_types(tiles)

        assert result == 6

    def test_counts_honors_correctly(self):
        """Correctly counts honor tiles (winds and dragons)."""
        # E, S, W, N, Haku, Hatsu, Chun
        tiles = TilesConverter.string_to_136_array(honors="1234567")

        result = _count_terminal_honor_types(tiles)

        assert result == 7

    def test_ignores_middle_tiles(self):
        """Does not count middle tiles (2-8 of each suit)."""
        # 2m, 5m, 3p, 8p, 4s, 8s
        tiles = TilesConverter.string_to_136_array(man="25", pin="38", sou="48")

        result = _count_terminal_honor_types(tiles)

        assert result == 0

    def test_mixed_hand(self):
        """Correctly counts mixed hand of terminals, honors, and middle tiles."""
        # 1m, 5m, 9m, 1p, E, S (3 terminals + 2 honors = 5, ignoring 5m)
        tiles = TilesConverter.string_to_136_array(man="159", pin="1", honors="12")

        result = _count_terminal_honor_types(tiles)

        assert result == 5

    def test_empty_hand(self):
        """Returns 0 for empty hand."""
        result = _count_terminal_honor_types([])

        assert result == 0

    def test_all_13_types(self):
        """Counts all 13 terminal/honor types correctly."""
        # all terminal/honors: 1m 9m 1p 9p 1s 9s E S W N Haku Hatsu Chun
        tiles = TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="1234567")

        result = _count_terminal_honor_types(tiles)

        assert result == 13


class TestCallKyuushuKyuuhai:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        return MahjongRoundState(
            players=players,
            current_player_seat=0,
        )

    def test_returns_abortive_draw_result(self):
        """Returns correct result dict for abortive draw."""
        round_state = self._create_round_state()

        result = call_kyuushu_kyuuhai(round_state)

        assert result.type == "abortive_draw"
        assert result.reason == AbortiveDrawType.NINE_TERMINALS

    def test_includes_calling_player_seat(self):
        """Result includes the seat of the player who called."""
        round_state = self._create_round_state()
        round_state.current_player_seat = 2

        result = call_kyuushu_kyuuhai(round_state)

        assert result.seat == 2

    def test_different_seats(self):
        """Works correctly for any seat."""
        round_state = self._create_round_state()

        for seat in range(4):
            round_state.current_player_seat = seat
            result = call_kyuushu_kyuuhai(round_state)
            assert result.seat == seat


class TestKyuushuConstant:
    def test_minimum_types_is_9(self):
        """Verify the constant for minimum types is 9."""
        assert KYUUSHU_MIN_TYPES == 9


class TestCheckFourRiichi:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with 4 players."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        return MahjongRoundState(players=players)

    def test_four_riichi_returns_true(self):
        """Returns True when all 4 players have declared riichi."""
        round_state = self._create_round_state()
        for p in round_state.players:
            p.is_riichi = True

        result = check_four_riichi(round_state)

        assert result is True

    def test_three_riichi_returns_false(self):
        """Returns False when only 3 players have declared riichi."""
        round_state = self._create_round_state()
        round_state.players[0].is_riichi = True
        round_state.players[1].is_riichi = True
        round_state.players[2].is_riichi = True
        # player 3 has not declared riichi

        result = check_four_riichi(round_state)

        assert result is False

    def test_no_riichi_returns_false(self):
        """Returns False when no players have declared riichi."""
        round_state = self._create_round_state()

        result = check_four_riichi(round_state)

        assert result is False

    def test_one_riichi_returns_false(self):
        """Returns False when only 1 player has declared riichi."""
        round_state = self._create_round_state()
        round_state.players[2].is_riichi = True

        result = check_four_riichi(round_state)

        assert result is False


class TestCheckTripleRon:
    def test_three_callers_returns_true(self):
        """Returns True when 3 players call ron."""
        ron_callers = [0, 1, 2]

        result = check_triple_ron(ron_callers)

        assert result is True

    def test_two_callers_returns_false(self):
        """Returns False when only 2 players call ron (double ron is allowed)."""
        ron_callers = [1, 3]

        result = check_triple_ron(ron_callers)

        assert result is False

    def test_one_caller_returns_false(self):
        """Returns False when only 1 player calls ron."""
        ron_callers = [2]

        result = check_triple_ron(ron_callers)

        assert result is False

    def test_empty_callers_returns_false(self):
        """Returns False when no players call ron."""
        ron_callers = []

        result = check_triple_ron(ron_callers)

        assert result is False


class TestCheckFourKans:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with 4 players."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        return MahjongRoundState(players=players)

    def _create_kan_meld(self, tiles: list[int], meld_type: str = Meld.KAN) -> Meld:
        """Create a kan meld for testing."""
        return Meld(meld_type=meld_type, tiles=tiles, opened=True)

    def test_four_kans_by_multiple_players_returns_true(self):
        """Returns True when 4 kans declared by 2+ different players."""
        round_state = self._create_round_state()
        round_state.players[0].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(man="1111"))
        )
        round_state.players[0].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(pin="1111"))
        )
        round_state.players[1].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(sou="1111"))
        )
        round_state.players[2].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(honors="1111"))
        )

        result = check_four_kans(round_state)

        assert result is True

    def test_four_kans_by_one_player_returns_false(self):
        """Returns False when 4 kans declared by single player (suukantsu possible)."""
        round_state = self._create_round_state()
        round_state.players[0].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(man="1111"))
        )
        round_state.players[0].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(pin="1111"))
        )
        round_state.players[0].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(sou="1111"))
        )
        round_state.players[0].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(honors="1111"))
        )

        result = check_four_kans(round_state)

        assert result is False

    def test_three_kans_returns_false(self):
        """Returns False when only 3 kans have been declared."""
        round_state = self._create_round_state()
        round_state.players[0].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(man="1111"))
        )
        round_state.players[1].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(pin="1111"))
        )
        round_state.players[2].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(sou="1111"))
        )

        result = check_four_kans(round_state)

        assert result is False

    def test_no_kans_returns_false(self):
        """Returns False when no kans have been declared."""
        round_state = self._create_round_state()

        result = check_four_kans(round_state)

        assert result is False

    def test_shouminkan_counts_as_kan(self):
        """Shouminkan (added kan) counts towards the 4 kan limit."""
        round_state = self._create_round_state()
        round_state.players[0].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(man="1111"), Meld.SHOUMINKAN)
        )
        round_state.players[0].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(pin="1111"), Meld.KAN)
        )
        round_state.players[1].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(sou="1111"), Meld.SHOUMINKAN)
        )
        round_state.players[2].melds.append(
            self._create_kan_meld(TilesConverter.string_to_136_array(honors="1111"), Meld.KAN)
        )

        result = check_four_kans(round_state)

        assert result is True


class TestCheckFourWinds:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with 4 players."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        return MahjongRoundState(players=players)

    def test_four_east_winds_returns_true(self):
        """Returns True when first 4 discards are all East winds."""
        round_state = self._create_round_state()
        round_state.all_discards = TilesConverter.string_to_136_array(honors="1111")

        result = check_four_winds(round_state)

        assert result is True

    def test_four_south_winds_returns_true(self):
        """Returns True when first 4 discards are all South winds."""
        round_state = self._create_round_state()
        round_state.all_discards = TilesConverter.string_to_136_array(honors="2222")

        result = check_four_winds(round_state)

        assert result is True

    def test_four_west_winds_returns_true(self):
        """Returns True when first 4 discards are all West winds."""
        round_state = self._create_round_state()
        round_state.all_discards = TilesConverter.string_to_136_array(honors="3333")

        result = check_four_winds(round_state)

        assert result is True

    def test_four_north_winds_returns_true(self):
        """Returns True when first 4 discards are all North winds."""
        round_state = self._create_round_state()
        round_state.all_discards = TilesConverter.string_to_136_array(honors="4444")

        result = check_four_winds(round_state)

        assert result is True

    def test_mixed_winds_returns_false(self):
        """Returns False when first 4 discards are different wind tiles."""
        round_state = self._create_round_state()
        # E, S, W, N
        round_state.all_discards = TilesConverter.string_to_136_array(honors="1234")

        result = check_four_winds(round_state)

        assert result is False

    def test_non_wind_tiles_returns_false(self):
        """Returns False when first 4 discards are non-wind tiles."""
        round_state = self._create_round_state()
        # 1m tiles
        round_state.all_discards = TilesConverter.string_to_136_array(man="1111")

        result = check_four_winds(round_state)

        assert result is False

    def test_four_dragons_returns_false(self):
        """Returns False when first 4 discards are same dragon (not wind)."""
        round_state = self._create_round_state()
        round_state.all_discards = TilesConverter.string_to_136_array(honors="5555")

        result = check_four_winds(round_state)

        assert result is False

    def test_less_than_4_discards_returns_false(self):
        """Returns False when less than 4 discards have been made."""
        round_state = self._create_round_state()
        round_state.all_discards = TilesConverter.string_to_136_array(honors="111")[:3]

        result = check_four_winds(round_state)

        assert result is False

    def test_more_than_4_discards_returns_false(self):
        """Returns False when more than 4 discards have been made."""
        round_state = self._create_round_state()
        round_state.all_discards = [
            *TilesConverter.string_to_136_array(honors="1111"),
            TilesConverter.string_to_136_array(honors="22")[0],
        ]

        result = check_four_winds(round_state)

        assert result is False

    def test_open_meld_exists_returns_false(self):
        """Returns False when an open meld has been called."""
        round_state = self._create_round_state()
        round_state.all_discards = TilesConverter.string_to_136_array(honors="1111")
        round_state.players_with_open_hands = [1]

        result = check_four_winds(round_state)

        assert result is False


class TestAbortiveDrawType:
    def test_enum_values(self):
        """Verify enum has all required values."""
        assert AbortiveDrawType.NINE_TERMINALS.value == "nine_terminals"
        assert AbortiveDrawType.FOUR_RIICHI.value == "four_riichi"
        assert AbortiveDrawType.TRIPLE_RON.value == "triple_ron"
        assert AbortiveDrawType.FOUR_KANS.value == "four_kans"
        assert AbortiveDrawType.FOUR_WINDS.value == "four_winds"


class TestProcessAbortiveDraw:
    def _create_game_state(self) -> MahjongGameState:
        """Create a game state for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", score=25000),
            MahjongPlayer(seat=1, name="Bot1", score=25000),
            MahjongPlayer(seat=2, name="Bot2", score=25000),
            MahjongPlayer(seat=3, name="Bot3", score=25000),
        ]
        round_state = MahjongRoundState(players=players)
        return MahjongGameState(round_state=round_state, honba_sticks=0)

    def test_does_not_increment_honba(self):
        """Honba is not modified by process_abortive_draw (handled by process_round_end)."""
        game_state = self._create_game_state()
        initial_honba = game_state.honba_sticks

        process_abortive_draw(game_state, AbortiveDrawType.FOUR_RIICHI)

        assert game_state.honba_sticks == initial_honba

    def test_preserves_existing_honba(self):
        """Honba value is preserved (increment handled by process_round_end)."""
        game_state = self._create_game_state()
        game_state.honba_sticks = 3

        process_abortive_draw(game_state, AbortiveDrawType.NINE_TERMINALS)

        assert game_state.honba_sticks == 3

    def test_returns_abortive_draw_result(self):
        """Returns correct result dict structure."""
        game_state = self._create_game_state()

        result = process_abortive_draw(game_state, AbortiveDrawType.TRIPLE_RON)

        assert result.type == "abortive_draw"
        assert result.reason == AbortiveDrawType.TRIPLE_RON

    def test_includes_score_changes_of_zero(self):
        """Score changes in result are all zero."""
        game_state = self._create_game_state()

        result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_KANS)

        assert result.score_changes == {0: 0, 1: 0, 2: 0, 3: 0}

    def test_all_abortive_types_work(self):
        """Each abortive draw type is handled correctly."""
        for draw_type in AbortiveDrawType:
            game_state = self._create_game_state()
            result = process_abortive_draw(game_state, draw_type)

            assert result.type == "abortive_draw"
            assert result.reason == draw_type
