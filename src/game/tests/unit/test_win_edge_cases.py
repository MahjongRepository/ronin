"""
Unit tests for edge cases in win.py that were previously uncovered.

Tests cover:
1. Empty meld handling in all_tiles_from_hand_and_melds
2. Waiting tiles with 4-copy tile skipping
3. Chankan blocked by riichi furiten
4. Chankan blocked by temporary furiten
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.win import (
    all_tiles_from_hand_and_melds,
    get_waiting_tiles,
    is_chankan_possible,
)


class TestAllTilesFromHandAndMelds:
    def test_all_tiles_from_hand_with_empty_meld(self):
        """Test that empty melds are skipped when collecting all tiles."""
        # Create hand tiles: 123m
        hand_tiles = TilesConverter.string_to_136_array(man="123")

        # Create an empty meld (tiles=())
        empty_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(),
            opened=True,
        )

        # Create a normal meld: pon of 1p
        normal_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(pin="111")),
            opened=True,
        )

        # Call with both melds
        result = all_tiles_from_hand_and_melds(hand_tiles, [empty_meld, normal_meld])

        # Verify result contains hand tiles + normal meld tiles, but not empty meld
        assert len(result) == 6  # 3 from hand + 3 from normal meld
        # Verify the empty meld didn't add any tiles
        hand_tile_ids = set(hand_tiles)
        normal_meld_tiles = TilesConverter.string_to_136_array(pin="111")
        expected_ids = hand_tile_ids | set(normal_meld_tiles)
        assert set(result) == expected_ids


class TestWaitingTilesWithFourCopies:
    def test_waiting_tiles_skips_four_copy_tile(self):
        """Test that tiles with 4 copies are skipped in waiting tiles calculation.

        Hand: 1111m 23m 456p 78s 55s = 13 tiles.
        Tenpai structure: 111m(triplet) + 123m(sequence) + 456p + 78s(wait) + 55s(pair).
        Waiting on 6s (tile_34=23) and 9s (tile_34=26).
        The 4 copies of 1m (tile_34=0) should be skipped since tiles_34[0] >= 4.
        """
        tiles = TilesConverter.string_to_136_array(man="111123", pin="456", sou="5578")
        player = MahjongPlayer(
            seat=0,
            name="Player0",
            tiles=tuple(tiles),
        )

        # Get waiting tiles
        waiting = get_waiting_tiles(player)

        # Player should be waiting on 6s (tile_34 = 18 + 5 = 23) or 9s (tile_34 = 18 + 8 = 26)
        assert 23 in waiting or 26 in waiting

        # Verify that 1m (tile_34 = 0) is NOT in waiting tiles
        # The code skips it because we already have 4 copies
        assert 0 not in waiting

        # Additional verification: the hand is tenpai (waiting set is not empty)
        assert len(waiting) > 0


class TestChankanBlockedByRiichiFuriten:
    def test_chankan_blocked_by_riichi_furiten(self):
        """Test that chankan is blocked when player has riichi furiten."""
        # Create player who is tenpai waiting on 3p but has riichi furiten
        tiles_p0 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = (
            MahjongPlayer(
                seat=0,
                name="Player0",
                tiles=tuple(tiles_p0),
                is_riichi=True,
                is_riichi_furiten=True,  # Set riichi furiten flag
            ),
            MahjongPlayer(seat=1, name="Player1"),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        )

        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
        )

        # Player 2 tries to add kan of 3p (which player 0 is waiting on)
        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)

        # Player 0 should NOT be in chankan seats due to riichi furiten
        assert 0 not in chankan_seats
        assert chankan_seats == []


class TestChankanBlockedByTemporaryFuriten:
    def test_chankan_blocked_by_temporary_furiten(self):
        """Test that chankan is blocked when player has temporary furiten."""
        # Create player who is tenpai waiting on 3p but has temporary furiten
        tiles_p1 = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        players = (
            MahjongPlayer(seat=0, name="Player0"),
            MahjongPlayer(
                seat=1,
                name="Player1",
                tiles=tuple(tiles_p1),
                is_riichi=True,
                is_temporary_furiten=True,  # Set temporary furiten flag
            ),
            MahjongPlayer(seat=2, name="Player2"),
            MahjongPlayer(seat=3, name="Player3"),
        )

        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
        )

        # Player 2 tries to add kan of 3p (which player 1 is waiting on)
        kan_tile = TilesConverter.string_to_136_array(pin="3")[0]

        chankan_seats = is_chankan_possible(round_state, caller_seat=2, kan_tile=kan_tile)

        # Player 1 should NOT be in chankan seats due to temporary furiten
        assert 1 not in chankan_seats
        assert chankan_seats == []
