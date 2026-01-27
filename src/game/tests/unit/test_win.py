"""
Unit tests for win detection.
"""

from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.state import Discard, MahjongPlayer, MahjongRoundState
from game.logic.tiles import hand_to_34_array
from game.logic.win import (
    _melds_to_34_sets,
    can_call_ron,
    can_declare_tsumo,
    check_tsumo,
    get_waiting_tiles,
    is_chankan_possible,
    is_chiihou,
    is_furiten,
    is_haitei,
    is_houtei,
    is_tenhou,
)


class TestCheckTsumo:
    def test_winning_hand_all_triplets(self):
        # 111m 222m 333m 444m 55m (4 triplets + pair)
        tiles = TilesConverter.string_to_136_array(man="111222333444") + TilesConverter.string_to_136_array(
            man="55"
        )
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert check_tsumo(player) is True

    def test_winning_hand_all_sequences(self):
        # 123m 456m 789m 123p 55p (4 sequences + pair)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert check_tsumo(player) is True

    def test_winning_hand_mixed(self):
        # 123m 456p 789s 111z 55z (3 sequences + 1 triplet + pair)
        # using honors: 1=east, 5=haku
        tiles = TilesConverter.string_to_136_array(man="123", pin="456", sou="789", honors="11155")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert check_tsumo(player) is True

    def test_winning_hand_tanyao(self):
        # 234m 567m 234p 567s 55s (all simples)
        tiles = TilesConverter.string_to_136_array(man="234567", pin="234", sou="56755")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert check_tsumo(player) is True

    def test_non_winning_hand_one_away(self):
        # 123m 456m 789m 12p 55p (waiting for 3p)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert check_tsumo(player) is False

    def test_non_winning_hand_messy(self):
        # random tiles that don't form valid hand
        tiles = TilesConverter.string_to_136_array(man="1357", pin="2468", sou="13579")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert check_tsumo(player) is False

    def test_winning_hand_with_open_pon(self):
        # 234m 567m 234s (3 sequences) + PON(888p) + 55s pair
        # closed tiles (11) + pon tiles (3) = 14 total
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        all_tiles = closed_tiles + pon_tiles

        pon = Meld(
            meld_type=Meld.PON, tiles=pon_tiles, opened=True, called_tile=pon_tiles[0], who=0, from_who=1
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=all_tiles, melds=[pon])
        assert check_tsumo(player) is True

    def test_chiitoitsu_winning_hand(self):
        # 7 pairs: 11m 22m 33m 44p 55p 66s 77s
        tiles = TilesConverter.string_to_136_array(man="112233", pin="4455", sou="6677")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert check_tsumo(player) is True

    def test_kokushi_winning_hand(self):
        # 13 terminals/honors + one pair
        # 1m 9m 1p 9p 1s 9s + E S W N + Haku Hatsu Chun + one extra
        tiles = TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="12345677")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert check_tsumo(player) is True


class TestCanDeclareTsumo:
    def _create_round_state(self, dealer_seat: int = 0) -> MahjongRoundState:
        """Create a basic round state for testing."""
        return MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,  # east
            dora_indicators=[0],  # 1m as dora indicator
        )

    def test_closed_hand_can_declare(self):
        # closed winning hand - menzen tsumo is always valid
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is True

    def test_non_winning_hand_cannot_declare(self):
        # not a winning hand
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is False

    def test_open_hand_with_yakuhai_can_declare(self):
        # open hand with yakuhai (haku pon)
        # 234m 567m 234s (3 sequences) + PON(Haku) + 55s pair = 14 tiles
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        all_tiles = closed_tiles + haku_tiles

        pon = Meld(
            meld_type=Meld.PON, tiles=haku_tiles, opened=True, called_tile=haku_tiles[0], who=0, from_who=1
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=all_tiles, melds=[pon])
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is True

    def test_open_hand_without_yaku_cannot_declare(self):
        # open hand with no yaku (pon of 1m, no special tiles)
        # 234p 567s 234m (3 sequences) + PON(111m) + 55m pair = 14 tiles
        # no tanyao (has 1m), no yakuhai, no other yaku
        # win tile (5m) must be at the end for proper detection
        closed_tiles_before_win = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        win_tile = TilesConverter.string_to_136_array(man="5")[:1]
        pon_tiles = TilesConverter.string_to_136_array(man="111")

        # construct so win tile is last in closed portion
        all_tiles = closed_tiles_before_win + pon_tiles + win_tile

        pon = Meld(
            meld_type=Meld.PON, tiles=pon_tiles, opened=True, called_tile=pon_tiles[0], who=0, from_who=1
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=all_tiles, melds=[pon])
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is False

    def test_open_tanyao_with_kuitan_enabled(self):
        # open tanyao - with default settings (kuitan enabled), this should have yaku
        # 234m 567m 234s (3 sequences) + PON(888p) + 55s pair = 14 tiles
        # all simples = tanyao yaku
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        all_tiles = closed_tiles + pon_tiles

        pon = Meld(
            meld_type=Meld.PON, tiles=pon_tiles, opened=True, called_tile=pon_tiles[0], who=0, from_who=1
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=all_tiles, melds=[pon])
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is True

    def test_riichi_hand_can_declare(self):
        # closed riichi hand
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles, is_riichi=True)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is True

    def test_ippatsu_hand_can_declare(self):
        # riichi with ippatsu
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles, is_riichi=True, is_ippatsu=True)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is True


class TestGetWaitingTiles:
    def test_tempai_single_wait(self):
        # 123m 456m 789m 123p 5p - waiting for 5p (penchan wait doesn't exist here)
        # let's use a clearer example: 123m 456m 789m 234p 5p - waiting for 5p
        # actually for valid tempai: 123m 456m 789m 12p waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)

        waiting = get_waiting_tiles(player)

        # waiting for 3p (tile_34 = 11, which is 3p in 34 format: 9man + 2pin offset)
        # pin tiles start at index 9 in 34-format, so 3p = 9 + 2 = 11
        assert 11 in waiting  # 3p

    def test_tempai_multiple_waits(self):
        # 123m 456m 789m 45p 5p - waiting for 3p or 6p (ryanmen wait)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="4555")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)

        waiting = get_waiting_tiles(player)

        # waiting for 3p (index 11) or 6p (index 14)
        assert 11 in waiting  # 3p
        assert 14 in waiting  # 6p

    def test_not_tempai_no_waiting_tiles(self):
        # random tiles not in tempai
        tiles = TilesConverter.string_to_136_array(man="1357", pin="2468", sou="13579")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)

        waiting = get_waiting_tiles(player)

        assert len(waiting) == 0

    def test_tempai_tanki_wait(self):
        # 111m 222m 333m 444m 5m - tanki wait for 5m
        tiles = TilesConverter.string_to_136_array(man="1112223334445")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)

        waiting = get_waiting_tiles(player)

        # waiting for 5m (tile_34 = 4)
        assert 4 in waiting  # 5m

    def test_chiitoitsu_wait(self):
        # 6 pairs + single tile: 11m 22m 33m 44p 55p 66s 7s
        tiles = TilesConverter.string_to_136_array(man="112233", pin="4455", sou="667")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)

        waiting = get_waiting_tiles(player)

        # waiting for 7s (tile_34 = 18 + 6 = 24)
        assert 24 in waiting  # 7s


class TestIsFuriten:
    def test_not_furiten_no_discards(self):
        # tempai hand with no discards
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)

        assert is_furiten(player) is False

    def test_not_furiten_irrelevant_discards(self):
        # tempai waiting for 3p, discarded unrelated tiles
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        # discard 1m (tile_id 0)
        discards = [Discard(tile_id=0)]
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles, discards=discards)

        assert is_furiten(player) is False

    def test_furiten_discarded_waiting_tile(self):
        # tempai waiting for 3p, already discarded 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        # 3p in 136-format: pin starts at 36, 3p = 36 + 8 = 44 (for first 3p)
        discards = [Discard(tile_id=44)]  # 3p
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles, discards=discards)

        assert is_furiten(player) is True

    def test_furiten_multiple_discards_one_waiting(self):
        # tempai waiting for 3p or 6p, discarded 6p (one of the waits)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="4555")
        # 6p in 136-format: 36 + 20 = 56 (first 6p)
        discards = [Discard(tile_id=0), Discard(tile_id=56)]  # 1m, 6p
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles, discards=discards)

        assert is_furiten(player) is True

    def test_not_tempai_not_furiten(self):
        # not in tempai, can't be furiten
        tiles = TilesConverter.string_to_136_array(man="1357", pin="2468", sou="13579")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)

        assert is_furiten(player) is False


class TestCanCallRon:
    def _create_round_state(self, dealer_seat: int = 0) -> MahjongRoundState:
        """Create a basic round state for testing."""
        return MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,  # east
            dora_indicators=[0],  # 1m as dora indicator
        )

    def test_can_ron_closed_hand(self):
        # closed tempai hand, discard completes it
        # 123m 456m 789m 12p waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles, is_riichi=True)
        round_state = self._create_round_state()

        # 3p tile
        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]

        assert can_call_ron(player, discarded_tile, round_state) is True

    def test_cannot_ron_furiten(self):
        # tempai but furiten (discarded 3p)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        # discarded 3p already
        discards = [Discard(tile_id=44)]  # 3p
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles, discards=discards, is_riichi=True)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]

        assert can_call_ron(player, discarded_tile, round_state) is False

    def test_cannot_ron_wrong_tile(self):
        # tile doesn't complete hand
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles, is_riichi=True)
        round_state = self._create_round_state()

        # 9s doesn't complete this hand
        discarded_tile = TilesConverter.string_to_136_array(sou="9")[0]

        assert can_call_ron(player, discarded_tile, round_state) is False

    def test_can_ron_open_hand_with_yaku(self):
        # open hand with yakuhai (haku pon), can ron with yaku
        # 234m 567m 23s (sequences) + PON(Haku) waiting for 1s or 4s
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        all_tiles = closed_tiles + haku_tiles

        pon = Meld(
            meld_type=Meld.PON, tiles=haku_tiles, opened=True, called_tile=haku_tiles[0], who=0, from_who=1
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=all_tiles, melds=[pon])
        round_state = self._create_round_state()

        # 4s completes the hand
        discarded_tile = TilesConverter.string_to_136_array(sou="4")[0]

        assert can_call_ron(player, discarded_tile, round_state) is True

    def test_cannot_ron_open_hand_no_yaku(self):
        # open hand without yaku (no yakuhai, no tanyao due to 1m)
        # 234p 567s 23m (sequences) + PON(111m) waiting for 1m or 4m
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        all_tiles = closed_tiles + pon_tiles

        pon = Meld(
            meld_type=Meld.PON, tiles=pon_tiles, opened=True, called_tile=pon_tiles[0], who=0, from_who=1
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=all_tiles, melds=[pon])
        round_state = self._create_round_state()

        # 6m completes the hand but no yaku
        discarded_tile = TilesConverter.string_to_136_array(man="6")[0]

        assert can_call_ron(player, discarded_tile, round_state) is False

    def test_can_ron_open_tanyao(self):
        # open hand with tanyao (all simples)
        # 234m 567m 234p 5s + PON(888s) waiting for 5s to make pair
        # hand before ron: 10 closed + 3 pon = 13 tiles
        closed_tiles = TilesConverter.string_to_136_array(man="234567", pin="234", sou="5")
        pon_tiles = TilesConverter.string_to_136_array(sou="888")
        all_tiles = closed_tiles + pon_tiles

        pon = Meld(
            meld_type=Meld.PON, tiles=pon_tiles, opened=True, called_tile=pon_tiles[0], who=0, from_who=1
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=all_tiles, melds=[pon])
        round_state = self._create_round_state()

        # 5s completes the pair for tanyao (use different tile ID than the one in hand)
        # hand has 5s (tile 88), so use 89 for the discarded 5s
        discarded_tile = 89  # second 5s tile

        assert can_call_ron(player, discarded_tile, round_state) is True


class TestHandTo34Array:
    def test_simple_hand(self):
        # 111m (tile_ids 0,1,2) -> tile_34 index 0 should have count 3
        tiles = [0, 1, 2]
        result = hand_to_34_array(tiles)
        assert result[0] == 3  # 1m count
        assert sum(result) == 3

    def test_mixed_suits(self):
        # 1m, 1p, 1s
        tiles = [0, 36, 72]  # 1m, 1p, 1s
        result = hand_to_34_array(tiles)
        assert result[0] == 1  # 1m
        assert result[9] == 1  # 1p
        assert result[18] == 1  # 1s
        assert sum(result) == 3

    def test_honors(self):
        # E, S, W, N, Haku, Hatsu, Chun
        tiles = [108, 112, 116, 120, 124, 128, 132]
        result = hand_to_34_array(tiles)
        assert result[27] == 1  # east
        assert result[28] == 1  # south
        assert result[29] == 1  # west
        assert result[30] == 1  # north
        assert result[31] == 1  # haku
        assert result[32] == 1  # hatsu
        assert result[33] == 1  # chun


class TestMeldsTo34Sets:
    def test_no_melds(self):
        result = _melds_to_34_sets([])
        assert result is None

    def test_empty_list(self):
        result = _melds_to_34_sets([])
        assert result is None

    def test_pon_meld(self):
        # pon of 1m (tiles 0,1,2 -> tile_34 = 0)
        pon = Meld(meld_type=Meld.PON, tiles=[0, 1, 2], opened=True)
        result = _melds_to_34_sets([pon])
        assert result == [[0, 0, 0]]

    def test_chi_meld(self):
        # chi of 123m (tiles 0,4,8 -> tile_34 = 0,1,2)
        chi = Meld(meld_type=Meld.CHI, tiles=[0, 4, 8], opened=True)
        result = _melds_to_34_sets([chi])
        assert result == [[0, 1, 2]]

    def test_multiple_melds(self):
        # pon of 1m and chi of 123p
        pon = Meld(meld_type=Meld.PON, tiles=[0, 1, 2], opened=True)
        chi = Meld(meld_type=Meld.CHI, tiles=[36, 40, 44], opened=True)  # 1p,2p,3p
        result = _melds_to_34_sets([pon, chi])
        assert result == [[0, 0, 0], [9, 10, 11]]


class TestHasOpenMelds:
    def test_no_melds(self):
        player = MahjongPlayer(seat=0, name="Player1")
        assert player.has_open_melds() is False

    def test_open_pon(self):
        pon = Meld(meld_type=Meld.PON, tiles=[0, 1, 2], opened=True)
        player = MahjongPlayer(seat=0, name="Player1", melds=[pon])
        assert player.has_open_melds() is True

    def test_closed_kan(self):
        # closed kan is not an open meld
        kan = Meld(meld_type=Meld.KAN, tiles=[0, 1, 2, 3], opened=False)
        player = MahjongPlayer(seat=0, name="Player1", melds=[kan])
        assert player.has_open_melds() is False

    def test_mixed_melds(self):
        # one closed kan, one open pon
        kan = Meld(meld_type=Meld.KAN, tiles=[0, 1, 2, 3], opened=False)
        pon = Meld(meld_type=Meld.PON, tiles=[4, 5, 6], opened=True)
        player = MahjongPlayer(seat=0, name="Player1", melds=[kan, pon])
        assert player.has_open_melds() is True


class TestIsHaitei:
    def test_haitei_when_wall_empty(self):
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=[],  # empty wall = haitei
        )
        assert is_haitei(round_state) is True

    def test_not_haitei_when_wall_has_tiles(self):
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=[1, 2, 3],  # tiles in wall
        )
        assert is_haitei(round_state) is False


class TestIsHoutei:
    def test_houtei_when_wall_empty(self):
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=[],  # empty wall = houtei possible
        )
        assert is_houtei(round_state) is True

    def test_not_houtei_when_wall_has_tiles(self):
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=[1, 2, 3],
        )
        assert is_houtei(round_state) is False


class TestIsTenhou:
    def test_tenhou_dealer_first_draw(self):
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=[],  # no discards
            players_with_open_hands=[],  # no open melds
        )
        assert is_tenhou(players[0], round_state) is True

    def test_not_tenhou_non_dealer(self):
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=[],
            players_with_open_hands=[],
        )
        # player at seat 1 is not dealer
        assert is_tenhou(players[1], round_state) is False

    def test_not_tenhou_after_discards(self):
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=[1],  # discards have been made
            players_with_open_hands=[],
        )
        assert is_tenhou(players[0], round_state) is False

    def test_not_tenhou_after_meld(self):
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=[],
            players_with_open_hands=[1],  # someone called a meld
        )
        assert is_tenhou(players[0], round_state) is False


class TestIsChiihou:
    def test_chiihou_non_dealer_first_draw(self):
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=[],  # no discards
            players_with_open_hands=[],  # no open melds
        )
        # player at seat 1 (non-dealer) can have chiihou
        assert is_chiihou(players[1], round_state) is True

    def test_not_chiihou_dealer(self):
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=[],
            players_with_open_hands=[],
        )
        # dealer cannot have chiihou (would be tenhou)
        assert is_chiihou(players[0], round_state) is False

    def test_not_chiihou_after_discards(self):
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=[1],  # discards have been made
            players_with_open_hands=[],
        )
        assert is_chiihou(players[1], round_state) is False

    def test_not_chiihou_after_meld(self):
        players = [MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4)]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=[],
            players_with_open_hands=[2],  # someone called a meld
        )
        assert is_chiihou(players[1], round_state) is False


class TestIsChankanPossible:
    def test_chankan_when_waiting_on_tile(self):
        # player 0 is waiting for 3p (tempai hand 123m 456m 789m 12p 55p)
        tiles_p0 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0, is_riichi=True),
            MahjongPlayer(seat=1, name="Player1"),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            dora_indicators=[0],
        )

        # player 2 tries to add kan of 3p
        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert 0 in chankan_seats

    def test_no_chankan_when_not_waiting(self):
        # player 0 is waiting for 3p (tempai hand 123m 456m 789m 12p 55p)
        tiles_p0 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0, is_riichi=True),
            MahjongPlayer(seat=1, name="Player1"),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            dora_indicators=[0],
        )

        # player 2 tries to add kan of 9s (no one waiting on it)
        kan_tile = TilesConverter.string_to_136_array(sou="9")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert chankan_seats == []

    def test_no_chankan_when_furiten(self):
        # player 0 is waiting for 3p but has discarded 3p (furiten)
        tiles_p0 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards_p0 = [Discard(tile_id=44)]  # 3p already discarded
        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=tiles_p0, discards=discards_p0, is_riichi=True),
            MahjongPlayer(seat=1, name="Player1"),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            dora_indicators=[0],
        )

        # player 2 tries to add kan of 3p
        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert 0 not in chankan_seats

    def test_no_chankan_for_self(self):
        # player 2 is waiting for 3p and calls kan on 3p - they can't chankan themselves
        tiles_p2 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = [
            MahjongPlayer(seat=0, name="Player0"),
            MahjongPlayer(seat=1, name="Player1"),
            MahjongPlayer(seat=2, name="Player2", tiles=tiles_p2, is_riichi=True),
            MahjongPlayer(seat=3, name="Player3"),
        ]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            dora_indicators=[0],
        )

        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert 2 not in chankan_seats

    def test_multiple_chankan_players(self):
        # both player 0 and player 3 are waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = [
            MahjongPlayer(seat=0, name="Player0", tiles=list(tiles), is_riichi=True),
            MahjongPlayer(seat=1, name="Player1"),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3", tiles=list(tiles), is_riichi=True),
        ]
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            dora_indicators=[0],
        )

        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert 0 in chankan_seats
        assert 3 in chankan_seats
        assert len(chankan_seats) == 2
