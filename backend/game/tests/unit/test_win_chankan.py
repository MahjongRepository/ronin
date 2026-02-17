"""
Unit tests for chankan detection edge cases.

Tests is_chankan_possible with waiting/not-waiting/furiten/self/multiple players,
and open hand yaku validation.
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.settings import GameSettings
from game.logic.state import Discard, MahjongPlayer, MahjongRoundState
from game.logic.wall import Wall
from game.logic.win import (
    _has_yaku_for_open_hand,
    is_chankan_possible,
)


class TestIsChankanPossible:
    def test_chankan_when_waiting_on_tile(self):
        # player 0 is waiting for 3p (tempai hand 123m 456m 789m 12p 55p)
        tiles_p0 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = (
            MahjongPlayer(seat=0, name="Player0", tiles=tuple(tiles_p0), is_riichi=True, score=25000),
            MahjongPlayer(seat=1, name="Player1", score=25000),
            MahjongPlayer(seat=2, name="Player2", score=25000),
            MahjongPlayer(seat=3, name="Player3", score=25000),
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            wall=Wall(dora_indicators=tuple(TilesConverter.string_to_136_array(man="1"))),
        )

        # player 2 tries to add kan of 3p
        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert 0 in chankan_seats

    def test_no_chankan_when_not_waiting(self):
        # player 0 is waiting for 3p (tempai hand 123m 456m 789m 12p 55p)
        tiles_p0 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = (
            MahjongPlayer(seat=0, name="Player0", tiles=tuple(tiles_p0), is_riichi=True, score=25000),
            MahjongPlayer(seat=1, name="Player1", score=25000),
            MahjongPlayer(seat=2, name="Player2", score=25000),
            MahjongPlayer(seat=3, name="Player3", score=25000),
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            wall=Wall(dora_indicators=tuple(TilesConverter.string_to_136_array(man="1"))),
        )

        # player 2 tries to add kan of 9s (no one waiting on it)
        kan_tile = TilesConverter.string_to_136_array(sou="9")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert chankan_seats == []

    def test_no_chankan_when_furiten(self):
        # player 0 is waiting for 3p but has discarded 3p (furiten)
        tiles_p0 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards_p0 = (Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0]),)
        players = (
            MahjongPlayer(
                seat=0,
                name="Player0",
                tiles=tuple(tiles_p0),
                discards=discards_p0,
                is_riichi=True,
                score=25000,
            ),
            MahjongPlayer(seat=1, name="Player1", score=25000),
            MahjongPlayer(seat=2, name="Player2", score=25000),
            MahjongPlayer(seat=3, name="Player3", score=25000),
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            wall=Wall(dora_indicators=tuple(TilesConverter.string_to_136_array(man="1"))),
        )

        # player 2 tries to add kan of 3p
        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert 0 not in chankan_seats

    def test_no_chankan_for_self(self):
        # player 2 is waiting for 3p and calls kan on 3p - they can't chankan themselves
        tiles_p2 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = (
            MahjongPlayer(seat=0, name="Player0", score=25000),
            MahjongPlayer(seat=1, name="Player1", score=25000),
            MahjongPlayer(seat=2, name="Player2", tiles=tuple(tiles_p2), is_riichi=True, score=25000),
            MahjongPlayer(seat=3, name="Player3", score=25000),
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            wall=Wall(dora_indicators=tuple(TilesConverter.string_to_136_array(man="1"))),
        )

        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)
        assert 2 not in chankan_seats

    def test_multiple_chankan_players(self):
        # both player 0 and player 3 are waiting for 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = (
            MahjongPlayer(seat=0, name="Player0", tiles=tuple(tiles), is_riichi=True, score=25000),
            MahjongPlayer(seat=1, name="Player1", score=25000),
            MahjongPlayer(seat=2, name="Player2", score=25000),
            MahjongPlayer(seat=3, name="Player3", tiles=tuple(tiles), is_riichi=True, score=25000),
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            wall=Wall(dora_indicators=tuple(TilesConverter.string_to_136_array(man="1"))),
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
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(honors="555")),
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
            tiles=(*closed_tiles, *haku_tiles),
            melds=(pon_meld,),
            score=25000,
        )

        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(20)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
            players=(
                MahjongPlayer(seat=0, name="P0", score=25000),
                player1,
                MahjongPlayer(seat=2, name="P2", score=25000),
                MahjongPlayer(seat=3, name="P3", score=25000),
            ),
            players_with_open_hands=(1,),
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
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[2],
            who=1,
            from_who=0,
        )
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        player1 = MahjongPlayer(
            seat=1,
            name="P1",
            tiles=(*closed_tiles, *pon_tiles),
            melds=(pon_meld,),
            score=25000,
        )

        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(20)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
            players=(
                MahjongPlayer(seat=0, name="P0", score=25000),
                player1,
                MahjongPlayer(seat=2, name="P2", score=25000),
                MahjongPlayer(seat=3, name="P3", score=25000),
            ),
            players_with_open_hands=(1,),
        )

        # player 2 does added kan with 5m - player 1 is waiting on 5m
        kan_tile = TilesConverter.string_to_136_array(man="5")[0]
        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)

        # chankan itself provides a yaku, so player 1 can call chankan
        assert 1 in chankan_seats


class TestHasYakuForOpenHandEmptyTiles:
    def test_empty_tiles_returns_false(self):
        """Open hand with no tiles returns False (boundary guard)."""
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[2],
            who=0,
            from_who=1,
        )
        player = MahjongPlayer(seat=0, name="Player1", tiles=(), melds=(pon,), score=25000)
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(dora_indicators=tuple(TilesConverter.string_to_136_array(man="1"))),
        )
        result = _has_yaku_for_open_hand(player, round_state, GameSettings())
        assert result is False
