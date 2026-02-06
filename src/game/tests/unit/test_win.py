"""
Unit tests for core win detection.
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import (
    Discard,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.win import (
    can_call_ron,
    can_declare_tsumo,
    check_tsumo,
    get_waiting_tiles,
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
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        assert check_tsumo(player) is True

    def test_winning_hand_all_sequences(self):
        # 123m 456m 789m 123p 55p (4 sequences + pair)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        assert check_tsumo(player) is True

    def test_winning_hand_mixed(self):
        # 123m 456p 789s 111z 55z (3 sequences + 1 triplet + pair)
        # using honors: 1=east, 5=haku
        tiles = TilesConverter.string_to_136_array(man="123", pin="456", sou="789", honors="11155")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        assert check_tsumo(player) is True

    def test_winning_hand_tanyao(self):
        # 234m 567m 234p 567s 55s (all simples)
        tiles = TilesConverter.string_to_136_array(man="234567", pin="234", sou="56755")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        assert check_tsumo(player) is True

    def test_non_winning_hand_one_away(self):
        # 123m 456m 789m 12p 55p (waiting for 3p)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        assert check_tsumo(player) is False

    def test_non_winning_hand_messy(self):
        # random tiles that don't form valid hand
        tiles = TilesConverter.string_to_136_array(man="1357", pin="2468", sou="13579")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        assert check_tsumo(player) is False

    def test_winning_hand_with_open_pon(self):
        # 234m 567m 234s (3 sequences) + PON(888p) + 55s pair
        # closed tiles (11) + pon tiles (3) = 14 total
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        all_tiles = closed_tiles + pon_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,))
        assert check_tsumo(player) is True

    def test_winning_hand_with_open_pon_meld_tiles_removed_from_hand(self):
        # after call_pon, meld tiles are removed from player.tiles
        # hand: 234m 567m 234s 55s (closed) + PON(888p) (open meld)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        # only closed tiles in hand (meld tiles NOT in player.tiles)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,))
        assert check_tsumo(player) is True

    def test_chiitoitsu_winning_hand(self):
        # 7 pairs: 11m 22m 33m 44p 55p 66s 77s
        tiles = TilesConverter.string_to_136_array(man="112233", pin="4455", sou="6677")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        assert check_tsumo(player) is True

    def test_kokushi_winning_hand(self):
        # 13 terminals/honors + one pair
        # 1m 9m 1p 9p 1s 9s + E S W N + Haku Hatsu Chun + one extra
        tiles = TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="12345677")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        assert check_tsumo(player) is True


class TestCanDeclareTsumo:
    def _create_round_state(self, dealer_seat: int = 0) -> MahjongRoundState:
        """Create a basic round state for testing."""
        return MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,  # east
            wall=tuple(range(10)),  # non-empty wall to avoid haitei triggering
            dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),  # 1m as dora indicator
        )

    def test_closed_hand_can_declare(self):
        # closed winning hand - menzen tsumo is always valid
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is True

    def test_non_winning_hand_cannot_declare(self):
        # not a winning hand
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is False

    def test_open_hand_with_yakuhai_can_declare(self):
        # open hand with yakuhai (haku pon)
        # closed: 234m 567m 234s 55s (11 tiles) + PON(Haku) (meld, 3 tiles) = 14 tiles
        # meld tiles not in player.tiles (matching actual gameplay after call_pon)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,))
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

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,))
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is False

    def test_open_tanyao_with_kuitan_enabled(self):
        # open tanyao - with default settings (kuitan enabled), this should have yaku
        # closed: 234m 567m 234s 55s (11 tiles) + PON(888p) (meld, 3 tiles) = 14 tiles
        # all simples = tanyao yaku
        # meld tiles not in player.tiles (matching actual gameplay after call_pon)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,))
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is True

    def test_riichi_hand_can_declare(self):
        # closed riichi hand
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), is_riichi=True)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is True

    def test_ippatsu_hand_can_declare(self):
        # riichi with ippatsu
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), is_riichi=True, is_ippatsu=True)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state) is True


class TestGetWaitingTiles:
    def test_tempai_single_wait(self):
        # 123m 456m 789m 123p 5p - waiting for 5p (penchan wait doesn't exist here)
        # let's use a clearer example: 123m 456m 789m 234p 5p - waiting for 5p
        # actually for valid tempai: 123m 456m 789m 12p waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))

        waiting = get_waiting_tiles(player)

        # waiting for 3p (tile_34 = 11, which is 3p in 34 format: 9man + 2pin offset)
        # pin tiles start at index 9 in 34-format, so 3p = 9 + 2 = 11
        assert 11 in waiting  # 3p

    def test_tempai_multiple_waits(self):
        # 123m 456m 789m 45p 5p - waiting for 3p or 6p (ryanmen wait)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="4555")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))

        waiting = get_waiting_tiles(player)

        # waiting for 3p (index 11) or 6p (index 14)
        assert 11 in waiting  # 3p
        assert 14 in waiting  # 6p

    def test_not_tempai_no_waiting_tiles(self):
        # random tiles not in tempai
        tiles = TilesConverter.string_to_136_array(man="1357", pin="2468", sou="13579")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))

        waiting = get_waiting_tiles(player)

        assert len(waiting) == 0

    def test_tempai_tanki_wait(self):
        # 111m 222m 333m 444m 5m - tanki wait for 5m
        tiles = TilesConverter.string_to_136_array(man="1112223334445")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))

        waiting = get_waiting_tiles(player)

        # waiting for 5m (tile_34 = 4)
        assert 4 in waiting  # 5m

    def test_chiitoitsu_wait(self):
        # 6 pairs + single tile: 11m 22m 33m 44p 55p 66s 7s
        tiles = TilesConverter.string_to_136_array(man="112233", pin="4455", sou="667")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))

        waiting = get_waiting_tiles(player)

        # waiting for 7s (tile_34 = 18 + 6 = 24)
        assert 24 in waiting  # 7s

    def test_waiting_tiles_with_open_pon_meld_tiles_removed_from_hand(self):
        # after call_pon, meld tiles are removed from player.tiles
        # closed hand: 234m 567m 23s 55s (10 tiles) + PON(888p) (open meld, 3 tiles) = 13 total (tenpai)
        # waiting for 1s or 4s to complete 23s sequence
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        # only closed tiles in hand (meld tiles NOT in player.tiles)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,))

        waiting = get_waiting_tiles(player)

        # 1s = tile_34 index 18, 4s = tile_34 index 21
        assert 18 in waiting  # 1s
        assert 21 in waiting  # 4s


class TestIsFuriten:
    def test_not_furiten_no_discards(self):
        # tempai hand with no discards
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))

        assert is_furiten(player) is False

    def test_not_furiten_irrelevant_discards(self):
        # tempai waiting for 3p, discarded unrelated tiles
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        # discard 1m
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(man="1")[0]),)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards)

        assert is_furiten(player) is False

    def test_furiten_discarded_waiting_tile(self):
        # tempai waiting for 3p, already discarded 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0]),)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards)

        assert is_furiten(player) is True

    def test_furiten_multiple_discards_one_waiting(self):
        # tempai waiting for 3p or 6p, discarded 6p (one of the waits)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="4555")
        discards = (
            Discard(tile_id=TilesConverter.string_to_136_array(man="1")[0]),
            Discard(tile_id=TilesConverter.string_to_136_array(pin="6")[0]),
        )
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards)

        assert is_furiten(player) is True

    def test_not_tempai_not_furiten(self):
        # not in tempai, can't be furiten
        tiles = TilesConverter.string_to_136_array(man="1357", pin="2468", sou="13579")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))

        assert is_furiten(player) is False


class TestCanCallRonImmutable:
    def _create_round_state(self, dealer_seat: int = 0) -> MahjongRoundState:
        """Create a basic round state for testing."""
        return MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,  # east
            wall=tuple(range(10)),  # non-empty wall to avoid houtei triggering
            dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),  # 1m as dora indicator
        )

    def test_can_ron_closed_hand(self):
        # closed tempai hand, discard completes it
        # 123m 456m 789m 12p waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), is_riichi=True)
        round_state = self._create_round_state()

        # 3p tile
        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]

        assert can_call_ron(player, discarded_tile, round_state) is True

    def test_cannot_ron_furiten(self):
        # tempai but furiten (discarded 3p)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        # discarded 3p already
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0]),)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards, is_riichi=True)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]

        assert can_call_ron(player, discarded_tile, round_state) is False

    def test_cannot_ron_wrong_tile(self):
        # tile doesn't complete hand
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), is_riichi=True)
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

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,))
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

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,))
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

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,))
        round_state = self._create_round_state()

        # 5s completes the pair for tanyao (use different tile ID than the one in hand)
        discarded_tile = TilesConverter.string_to_136_array(sou="55")[1]

        assert can_call_ron(player, discarded_tile, round_state) is True

    def test_can_ron_open_hand_meld_tiles_removed_from_hand(self):
        # after call_pon in actual gameplay, meld tiles are removed from player.tiles
        # closed: 234m 567m 23s 55s (10 tiles) + PON(Haku) (meld, 3 tiles) = 13 total
        # waiting for 1s or 4s
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        # only closed tiles in hand (meld tiles NOT in player.tiles, matching actual gameplay)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,))
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="4")[0]

        assert can_call_ron(player, discarded_tile, round_state) is True

    def test_can_ron_open_chi_meld_tiles_removed_from_hand(self):
        # after call_chi in actual gameplay, meld tiles are removed from player.tiles
        # closed: 567m 23s 55s HakuHakuHaku (10 tiles) + CHI(234m) (meld, 3 tiles) = 13 total
        # waiting for 1s or 4s
        closed_tiles = TilesConverter.string_to_136_array(man="567", sou="2355", honors="555")
        chi_tiles = sorted(TilesConverter.string_to_136_array(man="234"))

        chi = FrozenMeld(
            meld_type=FrozenMeld.CHI,
            tiles=tuple(chi_tiles),
            opened=True,
            called_tile=chi_tiles[0],
            who=0,
            from_who=3,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(chi,))
        round_state = self._create_round_state()

        # 4s completes: 234m(chi) + 567m + 234s + 55s(pair) + HakuHakuHaku
        discarded_tile = TilesConverter.string_to_136_array(sou="4")[0]

        assert can_call_ron(player, discarded_tile, round_state) is True

    def test_can_call_ron_does_not_mutate_player_tiles(self):
        # can_call_ron uses immutable state - no mutation possible
        # closed: 234m 567m 23s 55s (10 tiles) + PON(Haku) (meld, 3 tiles) = 13 total
        # waiting for 1s or 4s
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,))
        round_state = self._create_round_state()

        tiles_before = player.tiles  # immutable tuple
        discarded_tile = TilesConverter.string_to_136_array(sou="4")[0]

        assert can_call_ron(player, discarded_tile, round_state) is True
        assert player.tiles == tiles_before  # unchanged (immutable)


class TestIsHaitei:
    def test_haitei_when_wall_empty(self):
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=(),  # empty wall = haitei
        )
        assert is_haitei(round_state) is True

    def test_not_haitei_when_wall_has_tiles(self):
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=(1, 2, 3),  # tiles in wall
        )
        assert is_haitei(round_state) is False


class TestIsHoutei:
    def test_houtei_when_wall_empty(self):
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=(),  # empty wall = houtei possible
        )
        assert is_houtei(round_state) is True

    def test_not_houtei_when_wall_has_tiles(self):
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=(1, 2, 3),
        )
        assert is_houtei(round_state) is False


class TestIsTenhou:
    def test_tenhou_dealer_first_draw(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),  # no discards
            players_with_open_hands=(),  # no open melds
        )
        assert is_tenhou(players[0], round_state) is True

    def test_not_tenhou_non_dealer(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        # player at seat 1 is not dealer
        assert is_tenhou(players[1], round_state) is False

    def test_not_tenhou_after_discards(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(1,),  # discards have been made
            players_with_open_hands=(),
        )
        assert is_tenhou(players[0], round_state) is False

    def test_not_tenhou_after_meld(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(1,),  # someone called a meld
        )
        assert is_tenhou(players[0], round_state) is False


class TestIsChiihou:
    def test_chiihou_non_dealer_first_draw(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),  # no discards
            players_with_open_hands=(),  # no open melds
        )
        # player at seat 1 (non-dealer) can have chiihou
        assert is_chiihou(players[1], round_state) is True

    def test_not_chiihou_dealer(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        # dealer cannot have chiihou (would be tenhou)
        assert is_chiihou(players[0], round_state) is False

    def test_not_chiihou_after_discards(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(1,),  # discards have been made
            players_with_open_hands=(),
        )
        assert is_chiihou(players[1], round_state) is False

    def test_not_chiihou_after_meld(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}") for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(2,),  # someone called a meld
        )
        assert is_chiihou(players[1], round_state) is False
