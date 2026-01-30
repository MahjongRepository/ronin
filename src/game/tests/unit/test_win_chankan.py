"""
Unit tests for chankan detection and utility functions.
"""

from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.state import Discard, MahjongPlayer, MahjongRoundState
from game.logic.tiles import hand_to_34_array
from game.logic.win import (
    _has_yaku_for_open_hand,
    _melds_to_34_sets,
    is_chankan_possible,
)


class TestHandTo34Array:
    def test_simple_hand(self):
        # 111m -> tile_34 index 0 should have count 3
        tiles = TilesConverter.string_to_136_array(man="111")
        result = hand_to_34_array(tiles)
        assert result[0] == 3  # 1m count
        assert sum(result) == 3

    def test_mixed_suits(self):
        # 1m, 1p, 1s
        tiles = TilesConverter.string_to_136_array(man="1", pin="1", sou="1")
        result = hand_to_34_array(tiles)
        assert result[0] == 1  # 1m
        assert result[9] == 1  # 1p
        assert result[18] == 1  # 1s
        assert sum(result) == 3

    def test_honors(self):
        # E, S, W, N, Haku, Hatsu, Chun
        tiles = TilesConverter.string_to_136_array(honors="1234567")
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
        # pon of 1m -> tile_34 = 0
        pon = Meld(meld_type=Meld.PON, tiles=TilesConverter.string_to_136_array(man="111"), opened=True)
        result = _melds_to_34_sets([pon])
        assert result == [[0, 0, 0]]

    def test_chi_meld(self):
        # chi of 123m -> tile_34 = 0,1,2
        chi = Meld(meld_type=Meld.CHI, tiles=TilesConverter.string_to_136_array(man="123"), opened=True)
        result = _melds_to_34_sets([chi])
        assert result == [[0, 1, 2]]

    def test_multiple_melds(self):
        # pon of 1m and chi of 123p
        pon = Meld(meld_type=Meld.PON, tiles=TilesConverter.string_to_136_array(man="111"), opened=True)
        chi = Meld(meld_type=Meld.CHI, tiles=TilesConverter.string_to_136_array(pin="123"), opened=True)
        result = _melds_to_34_sets([pon, chi])
        assert result == [[0, 0, 0], [9, 10, 11]]


class TestHasOpenMelds:
    def test_no_melds(self):
        player = MahjongPlayer(seat=0, name="Player1")
        assert player.has_open_melds() is False

    def test_open_pon(self):
        pon = Meld(meld_type=Meld.PON, tiles=TilesConverter.string_to_136_array(man="111"), opened=True)
        player = MahjongPlayer(seat=0, name="Player1", melds=[pon])
        assert player.has_open_melds() is True

    def test_closed_kan(self):
        # closed kan is not an open meld
        kan = Meld(meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(man="1111"), opened=False)
        player = MahjongPlayer(seat=0, name="Player1", melds=[kan])
        assert player.has_open_melds() is False

    def test_mixed_melds(self):
        # one closed kan, one open pon
        kan = Meld(meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(man="1111"), opened=False)
        pon = Meld(meld_type=Meld.PON, tiles=TilesConverter.string_to_136_array(man="222"), opened=True)
        player = MahjongPlayer(seat=0, name="Player1", melds=[kan, pon])
        assert player.has_open_melds() is True


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
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
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
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
        )

        # player 2 tries to add kan of 9s (no one waiting on it)
        kan_tile = TilesConverter.string_to_136_array(sou="9")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert chankan_seats == []

    def test_no_chankan_when_furiten(self):
        # player 0 is waiting for 3p but has discarded 3p (furiten)
        tiles_p0 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards_p0 = [Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0])]
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
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
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
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
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
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
        )

        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert 0 in chankan_seats
        assert 3 in chankan_seats
        assert len(chankan_seats) == 2


class TestChankanWithOpenHand:
    def test_chankan_open_hand_with_yaku_included(self):
        """Open-handed player waiting on kan tile with yaku is included in chankan."""
        # player 1 has an open hand with yakuhai (triple haku pon)
        # closed: 234m 567m 23s 55s = 10 tiles + pon(haku) = 13 total
        # waiting for 1s or 4s
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=TilesConverter.string_to_136_array(honors="555"),
            opened=True,
            called_tile=TilesConverter.string_to_136_array(honors="5")[0],
            who=1,
            from_who=0,
        )
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        player1 = MahjongPlayer(
            seat=1,
            name="P1",
            tiles=[*closed_tiles, *haku_tiles],
            melds=[pon_meld],
        )

        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            wall=list(range(20)),
            players=[
                MahjongPlayer(seat=0, name="P0"),
                player1,
                MahjongPlayer(seat=2, name="P2"),
                MahjongPlayer(seat=3, name="P3"),
            ],
            players_with_open_hands=[1],
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
        )

        # player 2 does added kan with 4s - player 1 is waiting on 4s
        kan_tile = TilesConverter.string_to_136_array(sou="4")[0]
        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)

        # player 1 has yakuhai (haku pon), so chankan is valid
        assert 1 in chankan_seats

    def test_chankan_open_hand_allowed_with_chankan_yaku(self):
        """Open-handed player can call chankan because chankan itself is a valid yaku."""
        # player 1 has an open hand with pon of 1m (no other yaku)
        # hand: 2345m 234p 567s + pon of 111m, waiting for 5m (to make 234m + 55m pair)
        # chankan provides the required yaku (1 han)
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=pon_tiles,
            opened=True,
            called_tile=pon_tiles[2],
            who=1,
            from_who=0,
        )
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        player1 = MahjongPlayer(
            seat=1,
            name="P1",
            tiles=[*closed_tiles, *pon_tiles],
            melds=[pon_meld],
        )

        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            wall=list(range(20)),
            players=[
                MahjongPlayer(seat=0, name="P0"),
                player1,
                MahjongPlayer(seat=2, name="P2"),
                MahjongPlayer(seat=3, name="P3"),
            ],
            players_with_open_hands=[1],
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
        )

        # player 2 does added kan with 5m - player 1 is waiting on 5m
        kan_tile = TilesConverter.string_to_136_array(man="5")[0]
        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)

        # chankan itself provides a yaku, so player 1 can call chankan
        assert 1 in chankan_seats


class TestHasYakuForOpenHandEmptyTiles:
    def test_empty_tiles_returns_false(self):
        """Open hand with no tiles returns False."""
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        pon = Meld(
            meld_type=Meld.PON, tiles=pon_tiles, opened=True, called_tile=pon_tiles[2], who=0, from_who=1
        )
        player = MahjongPlayer(seat=0, name="Player1", tiles=[], melds=[pon])
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            dora_indicators=TilesConverter.string_to_136_array(man="1"),
        )
        result = _has_yaku_for_open_hand(player, round_state)
        assert result is False
