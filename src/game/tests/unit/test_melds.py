"""
Unit tests for meld operations (pon, chi, kan).
"""

import pytest
from mahjong.meld import Meld

from game.logic.abortive import check_four_kans
from game.logic.enums import MeldCallType
from game.logic.melds import (
    call_added_kan,
    call_chi,
    call_closed_kan,
    call_open_kan,
    call_pon,
    can_call_added_kan,
    can_call_chi,
    can_call_closed_kan,
    can_call_open_kan,
    can_call_pon,
    get_kuikae_tiles,
    get_possible_added_kans,
    get_possible_closed_kans,
)
from game.logic.state import MahjongPlayer, MahjongRoundState


class TestCanCallPon:
    def _create_player(self, tiles: list[int], *, is_riichi: bool = False) -> MahjongPlayer:
        """Create a player with specified tiles."""
        return MahjongPlayer(seat=0, name="Test", tiles=tiles, is_riichi=is_riichi)

    def test_can_call_pon_with_two_matching_tiles(self):
        # player has 1m 1m in hand (tiles 0 and 1 are both 1m in 136-format)
        player = self._create_player([0, 1, 36, 72])

        # someone discards 1m (tile 2, also 1m)
        result = can_call_pon(player, discarded_tile=2)

        assert result is True

    def test_can_call_pon_with_three_matching_tiles(self):
        # player has 1m 1m 1m in hand
        player = self._create_player([0, 1, 2, 36])

        result = can_call_pon(player, discarded_tile=3)

        assert result is True

    def test_cannot_call_pon_with_one_matching_tile(self):
        # player has only one 1m
        player = self._create_player([0, 36, 72, 108])

        result = can_call_pon(player, discarded_tile=1)

        assert result is False

    def test_cannot_call_pon_with_no_matching_tiles(self):
        # player has no 1m tiles
        player = self._create_player([36, 72, 108, 4])

        result = can_call_pon(player, discarded_tile=0)

        assert result is False

    def test_cannot_call_pon_when_in_riichi(self):
        # player has matching tiles but is in riichi
        player = self._create_player([0, 1, 36, 72], is_riichi=True)

        result = can_call_pon(player, discarded_tile=2)

        assert result is False

    def test_can_call_pon_different_tile_copies(self):
        # player has tiles 0 and 2 (both 1m, different copies)
        player = self._create_player([0, 2, 36, 72])

        result = can_call_pon(player, discarded_tile=1)

        assert result is True

    def test_can_call_pon_honor_tiles(self):
        # player has East wind tiles (108 and 109)
        player = self._create_player([108, 109, 36, 72])

        # someone discards East (tile 110)
        result = can_call_pon(player, discarded_tile=110)

        assert result is True


class TestCallPon:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[0, 1, 36, 72]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[4, 5, 40, 76]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[8, 9, 44, 80]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[12, 13, 48, 84]),
        ]
        return MahjongRoundState(players=players, current_player_seat=1)

    def test_call_pon_removes_tiles_from_hand(self):
        round_state = self._create_round_state()
        # player 0 calls pon on 1m (tile 2) discarded by player 1
        # player 0 has tiles 0 and 1 (both 1m)

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        player = round_state.players[0]
        # should have removed tiles 0 and 1 (the two 1m tiles)
        assert len(player.tiles) == 2
        assert 36 in player.tiles
        assert 72 in player.tiles

    def test_call_pon_creates_meld(self):
        round_state = self._create_round_state()

        meld = call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        assert meld.type == Meld.PON
        assert meld.opened is True
        assert meld.called_tile == 2
        assert meld.who == 0
        assert meld.from_who == 1
        # meld tiles should be sorted and contain all 3 tiles
        assert sorted(meld.tiles) == [0, 1, 2]

    def test_call_pon_adds_meld_to_player(self):
        round_state = self._create_round_state()
        player = round_state.players[0]
        assert len(player.melds) == 0

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        assert len(player.melds) == 1
        assert player.melds[0].type == Meld.PON

    def test_call_pon_adds_to_open_hands(self):
        round_state = self._create_round_state()
        assert round_state.players_with_open_hands == []

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        assert 0 in round_state.players_with_open_hands

    def test_call_pon_does_not_duplicate_open_hands(self):
        round_state = self._create_round_state()
        round_state.players_with_open_hands = [0]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        assert round_state.players_with_open_hands == [0]

    def test_call_pon_clears_ippatsu(self):
        round_state = self._create_round_state()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True
        round_state.players[2].is_ippatsu = True

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_pon_sets_current_player_to_caller(self):
        round_state = self._create_round_state()
        assert round_state.current_player_seat == 1

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        assert round_state.current_player_seat == 0

    def test_call_pon_returns_meld(self):
        round_state = self._create_round_state()

        result = call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        assert isinstance(result, Meld)

    def test_call_pon_raises_when_not_enough_tiles(self):
        round_state = self._create_round_state()
        # player 0 only has one 1m tile
        round_state.players[0].tiles = [0, 36, 72, 108]

        with pytest.raises(ValueError, match="cannot call pon"):
            call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

    def test_call_pon_from_any_player(self):
        round_state = self._create_round_state()
        # player 2 calls pon on tile discarded by player 0
        round_state.players[2].tiles = [0, 1, 44, 80]
        round_state.current_player_seat = 0

        meld = call_pon(round_state, caller_seat=2, discarder_seat=0, tile_id=2)

        assert meld.from_who == 0
        assert meld.who == 2
        assert round_state.current_player_seat == 2

    def test_call_pon_selects_correct_tiles_when_multiple_copies(self):
        round_state = self._create_round_state()
        # player has three 1m tiles (0, 1, 3) and one other
        round_state.players[0].tiles = [0, 1, 3, 36]

        meld = call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        # should remove first 2 matching tiles found (0 and 1)
        player = round_state.players[0]
        assert len(player.tiles) == 2
        # remaining should be the third 1m (3) and the 1p (36)
        assert 3 in player.tiles
        assert 36 in player.tiles
        # meld should have 0, 1, and the called tile 2
        assert sorted(meld.tiles) == [0, 1, 2]


class TestCanCallChi:
    def _create_player(self, tiles: list[int], *, is_riichi: bool = False) -> MahjongPlayer:
        """Create a player with specified tiles."""
        return MahjongPlayer(seat=1, name="Test", tiles=tiles, is_riichi=is_riichi)

    def test_can_call_chi_lowest_in_sequence(self):
        # player has 2m and 3m, can chi a discarded 1m
        # 2m = tiles 4-7 (tile_34=1), 3m = tiles 8-11 (tile_34=2)
        player = self._create_player([4, 8, 36, 72])

        # someone at seat 0 discards 1m (tile 0), caller at seat 1 is kamicha
        result = can_call_chi(player, discarded_tile=0, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (4, 8)  # 2m, 3m

    def test_can_call_chi_middle_in_sequence(self):
        # player has 1m and 3m, can chi a discarded 2m
        # 1m = tiles 0-3 (tile_34=0), 3m = tiles 8-11 (tile_34=2)
        player = self._create_player([0, 8, 36, 72])

        # discarder at seat 0, caller at seat 1
        result = can_call_chi(player, discarded_tile=4, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (0, 8)  # 1m, 3m

    def test_can_call_chi_highest_in_sequence(self):
        # player has 7m and 8m, can chi a discarded 9m
        # 7m = tiles 24-27 (tile_34=6), 8m = tiles 28-31 (tile_34=7)
        player = self._create_player([24, 28, 36, 72])

        result = can_call_chi(player, discarded_tile=32, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (24, 28)  # 7m, 8m

    def test_can_call_chi_multiple_combinations(self):
        # player has 3m, 4m, 6m, can chi a discarded 5m
        # 3m = tiles 8-11, 4m = tiles 12-15, 6m = tiles 20-23
        # 5m = tiles 16-19 (discarded)
        # possible: 3m+4m (345), 4m+6m (456)
        player = self._create_player([8, 12, 20, 72])

        result = can_call_chi(player, discarded_tile=16, discarder_seat=0, caller_seat=1)

        assert len(result) == 2
        # check both combinations exist
        combinations = set(result)
        assert (8, 12) in combinations  # 3m+4m for 345
        assert (12, 20) in combinations  # 4m+6m for 456

    def test_can_call_chi_three_combinations(self):
        # player has 4m, 5m, 6m, can chi a discarded 5m
        # actually need 4, 5, 6 in hand to form: 456 (with called 5), 345 or 567
        # let's have 4m, 6m, 7m to form 456 or 567 with discarded 5m
        # 4m = 12-15, 5m = 16-19, 6m = 20-23, 7m = 24-27
        player = self._create_player([12, 20, 24, 72])

        result = can_call_chi(player, discarded_tile=16, discarder_seat=0, caller_seat=1)

        assert len(result) == 2
        combinations = set(result)
        assert (12, 20) in combinations  # 4m+6m for 456
        assert (20, 24) in combinations  # 6m+7m for 567

    def test_cannot_call_chi_not_kamicha(self):
        # player has tiles to form chi but is not to the left
        player = self._create_player([4, 8, 36, 72])

        # discarder at seat 0, caller at seat 2 (not kamicha)
        result = can_call_chi(player, discarded_tile=0, discarder_seat=0, caller_seat=2)

        assert result == []

    def test_cannot_call_chi_honor_tiles(self):
        # player has East tiles but cannot chi honors
        # East = tiles 108-111 (tile_34=27)
        player = self._create_player([108, 109, 36, 72])

        result = can_call_chi(player, discarded_tile=110, discarder_seat=0, caller_seat=1)

        assert result == []

    def test_cannot_call_chi_when_in_riichi(self):
        # player has tiles to form chi but is in riichi
        player = self._create_player([4, 8, 36, 72], is_riichi=True)

        result = can_call_chi(player, discarded_tile=0, discarder_seat=0, caller_seat=1)

        assert result == []

    def test_cannot_call_chi_missing_tiles(self):
        # player doesn't have the needed tiles
        player = self._create_player([4, 36, 72, 108])

        result = can_call_chi(player, discarded_tile=0, discarder_seat=0, caller_seat=1)

        assert result == []

    def test_can_call_chi_pin_suit(self):
        # test chi with pin (circles) suit
        # 1p = tiles 36-39, 2p = tiles 40-43, 3p = tiles 44-47
        player = self._create_player([40, 44, 0, 72])

        result = can_call_chi(player, discarded_tile=36, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (40, 44)  # 2p, 3p

    def test_can_call_chi_sou_suit(self):
        # test chi with sou (bamboo) suit
        # 7s = tiles 96-99, 8s = tiles 100-103, 9s = tiles 104-107
        player = self._create_player([96, 100, 0, 36])

        result = can_call_chi(player, discarded_tile=104, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (96, 100)  # 7s, 8s

    def test_can_call_chi_seat_wraparound(self):
        # test kamicha calculation with seat wraparound
        # discarder at seat 3, caller at seat 0 (0 = (3+1)%4)
        player = MahjongPlayer(seat=0, name="Test", tiles=[4, 8, 36, 72])

        result = can_call_chi(player, discarded_tile=0, discarder_seat=3, caller_seat=0)

        assert len(result) == 1

    def test_cannot_call_chi_wrong_suit(self):
        # player has tiles from different suit than discarded
        # has 2p, 3p but discarded is 1m
        player = self._create_player([40, 44, 72, 108])

        result = can_call_chi(player, discarded_tile=0, discarder_seat=0, caller_seat=1)

        assert result == []

    def test_can_call_chi_edge_case_1m(self):
        # 1m can only be in sequences 123
        player = self._create_player([4, 8, 36, 72])  # has 2m, 3m

        # can form 123
        result = can_call_chi(player, discarded_tile=0, discarder_seat=0, caller_seat=1)
        assert len(result) == 1

    def test_can_call_chi_edge_case_9m(self):
        # 9m can only be in sequences 789
        # 7m = 24-27, 8m = 28-31, 9m = 32-35
        player = self._create_player([24, 28, 36, 72])  # has 7m, 8m

        # can form 789
        result = can_call_chi(player, discarded_tile=32, discarder_seat=0, caller_seat=1)
        assert len(result) == 1


class TestCallChi:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[0, 4, 36, 72]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[8, 12, 40, 76]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[16, 20, 44, 80]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[24, 28, 48, 84]),
        ]
        return MahjongRoundState(players=players, current_player_seat=0)

    def test_call_chi_removes_tiles_from_hand(self):
        round_state = self._create_round_state()
        # player 1 has 3m (8) and 4m (12), calls chi on 2m (4) from player 0

        call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(8, 12))

        player = round_state.players[1]
        # should have removed tiles 8 and 12 (3m and 4m)
        assert len(player.tiles) == 2
        assert 40 in player.tiles
        assert 76 in player.tiles

    def test_call_chi_creates_meld(self):
        round_state = self._create_round_state()

        meld = call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(8, 12))

        assert meld.type == Meld.CHI
        assert meld.opened is True
        assert meld.called_tile == 4
        assert meld.who == 1
        assert meld.from_who == 0
        # meld tiles should be sorted and contain all 3 tiles
        assert sorted(meld.tiles) == [4, 8, 12]

    def test_call_chi_adds_meld_to_player(self):
        round_state = self._create_round_state()
        player = round_state.players[1]
        assert len(player.melds) == 0

        call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(8, 12))

        assert len(player.melds) == 1
        assert player.melds[0].type == Meld.CHI

    def test_call_chi_adds_to_open_hands(self):
        round_state = self._create_round_state()
        assert round_state.players_with_open_hands == []

        call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(8, 12))

        assert 1 in round_state.players_with_open_hands

    def test_call_chi_does_not_duplicate_open_hands(self):
        round_state = self._create_round_state()
        round_state.players_with_open_hands = [1]

        call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(8, 12))

        assert round_state.players_with_open_hands == [1]

    def test_call_chi_clears_ippatsu(self):
        round_state = self._create_round_state()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True
        round_state.players[2].is_ippatsu = True

        call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(8, 12))

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_chi_sets_current_player_to_caller(self):
        round_state = self._create_round_state()
        assert round_state.current_player_seat == 0

        call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(8, 12))

        assert round_state.current_player_seat == 1

    def test_call_chi_returns_meld(self):
        round_state = self._create_round_state()

        result = call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(8, 12))

        assert isinstance(result, Meld)

    def test_call_chi_with_wraparound_seat(self):
        round_state = self._create_round_state()
        # player 0 calls chi on tile from player 3 (seat wraparound case)
        round_state.players[0].tiles = [4, 8, 36, 72]  # has 2m, 3m
        round_state.current_player_seat = 3

        meld = call_chi(round_state, caller_seat=0, discarder_seat=3, tile_id=0, sequence_tiles=(4, 8))

        assert meld.from_who == 3
        assert meld.who == 0
        assert round_state.current_player_seat == 0

    def test_call_chi_raises_when_tile_not_in_hand(self):
        round_state = self._create_round_state()

        with pytest.raises(ValueError, match="not in list"):
            call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(0, 4))


class TestCanCallOpenKan:
    def _create_player(self, tiles: list[int], *, is_riichi: bool = False) -> MahjongPlayer:
        """Create a player with specified tiles."""
        return MahjongPlayer(seat=0, name="Test", tiles=tiles, is_riichi=is_riichi)

    def _create_round_state(self, player: MahjongPlayer, wall_count: int = 10) -> MahjongRoundState:
        """Create a round state with the given player and wall size."""
        players = [
            player,
            MahjongPlayer(seat=1, name="Bot1", is_bot=True),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True),
        ]
        return MahjongRoundState(players=players, wall=list(range(wall_count)))

    def test_can_call_open_kan_with_three_matching_tiles(self):
        # player has 1m 1m 1m in hand
        player = self._create_player([0, 1, 2, 36])
        round_state = self._create_round_state(player)

        result = can_call_open_kan(player, discarded_tile=3, round_state=round_state)

        assert result is True

    def test_cannot_call_open_kan_with_two_matching_tiles(self):
        # player has only 2 matching tiles
        player = self._create_player([0, 1, 36, 72])
        round_state = self._create_round_state(player)

        result = can_call_open_kan(player, discarded_tile=2, round_state=round_state)

        assert result is False

    def test_cannot_call_open_kan_when_in_riichi(self):
        # player is in riichi
        player = self._create_player([0, 1, 2, 36], is_riichi=True)
        round_state = self._create_round_state(player)

        result = can_call_open_kan(player, discarded_tile=3, round_state=round_state)

        assert result is False

    def test_cannot_call_open_kan_when_wall_too_small(self):
        # wall has less than 2 tiles
        player = self._create_player([0, 1, 2, 36])
        round_state = self._create_round_state(player, wall_count=1)

        result = can_call_open_kan(player, discarded_tile=3, round_state=round_state)

        assert result is False

    def test_cannot_call_open_kan_wall_empty(self):
        player = self._create_player([0, 1, 2, 36])
        round_state = self._create_round_state(player, wall_count=0)

        result = can_call_open_kan(player, discarded_tile=3, round_state=round_state)

        assert result is False

    def test_cannot_call_open_kan_when_max_kans_reached(self):
        # 4 kans already declared across players
        player = self._create_player([0, 1, 2, 36])
        round_state = self._create_round_state(player)
        # add 4 kan melds to other players
        kan_meld = Meld(meld_type=Meld.KAN, tiles=[40, 41, 42, 43], opened=True, who=1)
        round_state.players[1].melds = [
            kan_meld,
            Meld(meld_type=Meld.KAN, tiles=[44, 45, 46, 47], opened=True, who=1),
        ]
        round_state.players[2].melds = [Meld(meld_type=Meld.KAN, tiles=[48, 49, 50, 51], opened=True, who=2)]
        round_state.players[3].melds = [Meld(meld_type=Meld.KAN, tiles=[52, 53, 54, 55], opened=True, who=3)]

        result = can_call_open_kan(player, discarded_tile=3, round_state=round_state)

        assert result is False


class TestCanCallClosedKan:
    def _create_player(self, tiles: list[int], *, is_riichi: bool = False) -> MahjongPlayer:
        """Create a player with specified tiles."""
        return MahjongPlayer(seat=0, name="Test", tiles=tiles, is_riichi=is_riichi)

    def _create_round_state(self, player: MahjongPlayer, wall_count: int = 10) -> MahjongRoundState:
        """Create a round state with the given player and wall size."""
        players = [
            player,
            MahjongPlayer(seat=1, name="Bot1", is_bot=True),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True),
        ]
        return MahjongRoundState(players=players, wall=list(range(wall_count)))

    def test_can_call_closed_kan_with_four_tiles(self):
        # player has all 4 copies of 1m
        player = self._create_player([0, 1, 2, 3, 36, 40, 44, 48, 72, 76, 80, 84, 108])
        round_state = self._create_round_state(player)

        result = can_call_closed_kan(player, tile_34=0, round_state=round_state)

        assert result is True

    def test_cannot_call_closed_kan_with_three_tiles(self):
        # player has only 3 copies
        player = self._create_player([0, 1, 2, 36])
        round_state = self._create_round_state(player)

        result = can_call_closed_kan(player, tile_34=0, round_state=round_state)

        assert result is False

    def test_cannot_call_closed_kan_wall_too_small(self):
        player = self._create_player([0, 1, 2, 3, 36])
        round_state = self._create_round_state(player, wall_count=1)

        result = can_call_closed_kan(player, tile_34=0, round_state=round_state)

        assert result is False

    def test_closed_kan_in_riichi_typically_not_allowed(self):
        # in riichi, closed kan is only allowed if it doesn't change waits
        # for most hands with 4-of-a-kind, removing those tiles changes the hand structure
        #
        # hand: 1m 1m 1m 1m 2m 2m 2m 3m 3m 3m 4m 4m 5m
        # waits: 2m, 3m, 5m, 6m (various shanpon/ryanmen combinations)
        # kan on 1m would remove a triplet that's part of the hand structure
        tiles = [0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 12, 13, 16]
        player = self._create_player(tiles, is_riichi=True)
        round_state = self._create_round_state(player)

        result = can_call_closed_kan(player, tile_34=0, round_state=round_state)

        # removing the 1m quad changes the hand structure, so kan is not allowed
        assert result is False

    def test_closed_kan_in_riichi_tile_is_wait(self):
        # hand where the 4-of-a-kind tile is one of the waiting tiles
        # even if structure would be preserved, can't kan on a wait tile
        #
        # for this test, we verify the check catches this case
        # hand: 9m 9m 9m 9m 1m 2m 3m 4m 5m 6m 7m 8m N
        # if 9m is a wait, kan should be rejected
        tiles = [32, 33, 34, 35, 0, 4, 8, 12, 16, 20, 24, 28, 124]
        player = self._create_player(tiles, is_riichi=True)
        round_state = self._create_round_state(player)

        result = can_call_closed_kan(player, tile_34=8, round_state=round_state)

        # 9m is involved in potential winning patterns, kan is not allowed
        assert result is False

    def test_cannot_call_closed_kan_when_max_kans_reached(self):
        # 4 kans already declared across players
        player = self._create_player([0, 1, 2, 3, 36, 40, 44, 48, 72, 76, 80, 84, 108])
        round_state = self._create_round_state(player)
        round_state.players[1].melds = [
            Meld(meld_type=Meld.KAN, tiles=[52, 53, 54, 55], opened=True, who=1),
            Meld(meld_type=Meld.KAN, tiles=[56, 57, 58, 59], opened=True, who=1),
        ]
        round_state.players[2].melds = [
            Meld(meld_type=Meld.KAN, tiles=[60, 61, 62, 63], opened=True, who=2),
            Meld(meld_type=Meld.KAN, tiles=[64, 65, 66, 67], opened=True, who=2),
        ]

        result = can_call_closed_kan(player, tile_34=0, round_state=round_state)

        assert result is False


class TestCanCallAddedKan:
    def _create_player_with_pon(self, hand_tiles: list[int], pon_tile_34: int) -> MahjongPlayer:
        """Create a player with a pon meld."""
        player = MahjongPlayer(seat=0, name="Test", tiles=hand_tiles)
        # create a pon meld
        pon_tiles = [pon_tile_34 * 4, pon_tile_34 * 4 + 1, pon_tile_34 * 4 + 2]
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=pon_tiles,
            opened=True,
            called_tile=pon_tiles[2],
            who=0,
            from_who=1,
        )
        player.melds.append(pon_meld)
        return player

    def _create_round_state(self, player: MahjongPlayer, wall_count: int = 10) -> MahjongRoundState:
        """Create a round state with the given player and wall size."""
        players = [
            player,
            MahjongPlayer(seat=1, name="Bot1", is_bot=True),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True),
        ]
        return MahjongRoundState(players=players, wall=list(range(wall_count)))

    def test_can_call_added_kan_with_pon_and_fourth_tile(self):
        # player has pon of 1m and the 4th 1m in hand
        # pon uses tiles 0, 1, 2 - 4th tile is 3
        player = self._create_player_with_pon([3, 36, 72, 108], pon_tile_34=0)
        round_state = self._create_round_state(player)

        result = can_call_added_kan(player, tile_34=0, round_state=round_state)

        assert result is True

    def test_cannot_call_added_kan_no_pon(self):
        # player has 4th tile but no pon
        player = MahjongPlayer(seat=0, name="Test", tiles=[0, 36, 72, 108])
        round_state = self._create_round_state(player)

        result = can_call_added_kan(player, tile_34=0, round_state=round_state)

        assert result is False

    def test_cannot_call_added_kan_no_fourth_tile(self):
        # player has pon but no 4th tile in hand
        player = self._create_player_with_pon([36, 72, 108, 112], pon_tile_34=0)
        round_state = self._create_round_state(player)

        result = can_call_added_kan(player, tile_34=0, round_state=round_state)

        assert result is False

    def test_cannot_call_added_kan_when_in_riichi(self):
        # player is in riichi
        player = self._create_player_with_pon([3, 36, 72, 108], pon_tile_34=0)
        player.is_riichi = True
        round_state = self._create_round_state(player)

        result = can_call_added_kan(player, tile_34=0, round_state=round_state)

        assert result is False

    def test_cannot_call_added_kan_wall_too_small(self):
        player = self._create_player_with_pon([3, 36, 72, 108], pon_tile_34=0)
        round_state = self._create_round_state(player, wall_count=1)

        result = can_call_added_kan(player, tile_34=0, round_state=round_state)

        assert result is False

    def test_cannot_call_added_kan_when_max_kans_reached(self):
        # 4 kans already declared across players
        player = self._create_player_with_pon([3, 36, 72, 108], pon_tile_34=0)
        round_state = self._create_round_state(player)
        round_state.players[1].melds = [
            Meld(meld_type=Meld.KAN, tiles=[40, 41, 42, 43], opened=True, who=1),
            Meld(meld_type=Meld.KAN, tiles=[44, 45, 46, 47], opened=True, who=1),
        ]
        round_state.players[2].melds = [
            Meld(meld_type=Meld.KAN, tiles=[48, 49, 50, 51], opened=True, who=2),
            Meld(meld_type=Meld.SHOUMINKAN, tiles=[52, 53, 54, 55], opened=True, who=2),
        ]

        result = can_call_added_kan(player, tile_34=0, round_state=round_state)

        assert result is False


class TestCallOpenKan:
    def _create_round_state_with_dead_wall(self) -> MahjongRoundState:
        """Create a round state with proper dead wall setup."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[0, 1, 2, 36, 40, 44, 48, 72, 76, 80, 84, 108, 112]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[4, 5, 6, 52]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[8, 9, 10, 56]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[12, 13, 14, 60]),
        ]
        return MahjongRoundState(
            players=players,
            current_player_seat=1,
            wall=list(range(120, 136)),  # 16 tiles in wall
            dead_wall=[116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129],
            dora_indicators=[118],  # first dora at index 2
        )

    def test_call_open_kan_removes_tiles_from_hand(self):
        round_state = self._create_round_state_with_dead_wall()
        # player 0 calls kan on 1m (tile 3) discarded by player 1
        # player 0 has tiles 0, 1, 2 (all 1m)

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=3)

        player = round_state.players[0]
        # should have removed 3 tiles (0, 1, 2) and added one from dead wall
        # original: 13 tiles, removed 3, added 1 = 11 tiles
        assert 0 not in player.tiles
        assert 1 not in player.tiles
        assert 2 not in player.tiles

    def test_call_open_kan_creates_meld(self):
        round_state = self._create_round_state_with_dead_wall()

        meld = call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=3)

        assert meld.type == Meld.KAN
        assert meld.opened is True
        assert meld.called_tile == 3
        assert meld.who == 0
        assert meld.from_who == 1
        assert len(meld.tiles) == 4
        assert sorted(meld.tiles) == [0, 1, 2, 3]

    def test_call_open_kan_adds_to_open_hands(self):
        round_state = self._create_round_state_with_dead_wall()
        assert round_state.players_with_open_hands == []

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=3)

        assert 0 in round_state.players_with_open_hands

    def test_call_open_kan_clears_ippatsu(self):
        round_state = self._create_round_state_with_dead_wall()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=3)

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_open_kan_defers_dora_indicator(self):
        round_state = self._create_round_state_with_dead_wall()
        initial_dora_count = len(round_state.dora_indicators)

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=3)

        # open kan defers dora reveal until after discard
        assert len(round_state.dora_indicators) == initial_dora_count
        assert round_state.pending_dora_count == 1

    def test_call_open_kan_maintains_dead_wall_size(self):
        round_state = self._create_round_state_with_dead_wall()

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=3)

        # dead wall stays at 14 (one drawn, one replenished from live wall)
        assert len(round_state.dead_wall) == 14

    def test_call_open_kan_sets_rinshan_flag(self):
        round_state = self._create_round_state_with_dead_wall()

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=3)

        assert round_state.players[0].is_rinshan is True

    def test_call_open_kan_sets_current_player(self):
        round_state = self._create_round_state_with_dead_wall()
        assert round_state.current_player_seat == 1

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=3)

        assert round_state.current_player_seat == 0

    def test_call_open_kan_raises_when_not_enough_tiles(self):
        round_state = self._create_round_state_with_dead_wall()
        round_state.players[0].tiles = [0, 1, 36, 72]  # only 2 matching tiles

        with pytest.raises(ValueError, match="cannot call open kan"):
            call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=3)


class TestCallClosedKan:
    def _create_round_state_with_dead_wall(self) -> MahjongRoundState:
        """Create a round state with proper dead wall setup."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[0, 1, 2, 3, 36, 40, 44, 48, 72, 76, 80, 84, 108]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[4, 5, 6, 52]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[8, 9, 10, 56]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[12, 13, 14, 60]),
        ]
        return MahjongRoundState(
            players=players,
            current_player_seat=0,
            wall=list(range(120, 136)),
            dead_wall=[116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129],
            dora_indicators=[118],
        )

    def test_call_closed_kan_removes_tiles_from_hand(self):
        round_state = self._create_round_state_with_dead_wall()

        call_closed_kan(round_state, seat=0, tile_id=0)

        player = round_state.players[0]
        # all 4 copies of 1m should be removed
        assert 0 not in player.tiles
        assert 1 not in player.tiles
        assert 2 not in player.tiles
        assert 3 not in player.tiles

    def test_call_closed_kan_creates_closed_meld(self):
        round_state = self._create_round_state_with_dead_wall()

        meld = call_closed_kan(round_state, seat=0, tile_id=0)

        assert meld.type == Meld.KAN
        assert meld.opened is False  # closed kan
        assert meld.who == 0
        assert len(meld.tiles) == 4

    def test_call_closed_kan_does_not_add_to_open_hands(self):
        round_state = self._create_round_state_with_dead_wall()
        assert round_state.players_with_open_hands == []

        call_closed_kan(round_state, seat=0, tile_id=0)

        # closed kan keeps hand closed
        assert 0 not in round_state.players_with_open_hands

    def test_call_closed_kan_clears_ippatsu(self):
        round_state = self._create_round_state_with_dead_wall()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True

        call_closed_kan(round_state, seat=0, tile_id=0)

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_closed_kan_adds_dora_indicator_immediately(self):
        round_state = self._create_round_state_with_dead_wall()
        initial_dora_count = len(round_state.dora_indicators)

        call_closed_kan(round_state, seat=0, tile_id=0)

        # closed kan reveals dora immediately (not deferred)
        assert len(round_state.dora_indicators) == initial_dora_count + 1
        assert round_state.pending_dora_count == 0

    def test_call_closed_kan_maintains_dead_wall_size(self):
        round_state = self._create_round_state_with_dead_wall()

        call_closed_kan(round_state, seat=0, tile_id=0)

        # dead wall stays at 14 (one drawn, one replenished from live wall)
        assert len(round_state.dead_wall) == 14

    def test_call_closed_kan_sets_rinshan_flag(self):
        round_state = self._create_round_state_with_dead_wall()

        call_closed_kan(round_state, seat=0, tile_id=0)

        assert round_state.players[0].is_rinshan is True

    def test_call_closed_kan_raises_when_not_enough_tiles(self):
        round_state = self._create_round_state_with_dead_wall()
        round_state.players[0].tiles = [0, 1, 2, 36]  # only 3 matching tiles

        with pytest.raises(ValueError, match="cannot call closed kan"):
            call_closed_kan(round_state, seat=0, tile_id=0)


class TestCallAddedKan:
    def _create_round_state_with_pon(self) -> MahjongRoundState:
        """Create a round state where player 0 has a pon and 4th tile."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[3, 36, 40, 44, 48, 72, 76, 80, 84, 108]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[4, 5, 6, 52]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[8, 9, 10, 56]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[12, 13, 14, 60]),
        ]
        # add pon meld to player 0
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=[0, 1, 2],
            opened=True,
            called_tile=2,
            who=0,
            from_who=1,
        )
        players[0].melds.append(pon_meld)

        return MahjongRoundState(
            players=players,
            current_player_seat=0,
            wall=list(range(120, 136)),
            dead_wall=[116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129],
            dora_indicators=[118],
            players_with_open_hands=[0],
        )

    def test_call_added_kan_removes_tile_from_hand(self):
        round_state = self._create_round_state_with_pon()

        call_added_kan(round_state, seat=0, tile_id=3)

        player = round_state.players[0]
        assert 3 not in player.tiles

    def test_call_added_kan_upgrades_pon_to_shouminkan(self):
        round_state = self._create_round_state_with_pon()

        meld = call_added_kan(round_state, seat=0, tile_id=3)

        assert meld.type == Meld.SHOUMINKAN
        assert meld.opened is True
        assert len(meld.tiles) == 4
        assert sorted(meld.tiles) == [0, 1, 2, 3]

    def test_call_added_kan_replaces_pon_meld(self):
        round_state = self._create_round_state_with_pon()
        player = round_state.players[0]
        assert len(player.melds) == 1
        assert player.melds[0].type == Meld.PON

        call_added_kan(round_state, seat=0, tile_id=3)

        assert len(player.melds) == 1
        assert player.melds[0].type == Meld.SHOUMINKAN

    def test_call_added_kan_clears_ippatsu(self):
        round_state = self._create_round_state_with_pon()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True

        call_added_kan(round_state, seat=0, tile_id=3)

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_added_kan_defers_dora_indicator(self):
        round_state = self._create_round_state_with_pon()
        initial_dora_count = len(round_state.dora_indicators)

        call_added_kan(round_state, seat=0, tile_id=3)

        # added kan defers dora reveal until after discard
        assert len(round_state.dora_indicators) == initial_dora_count
        assert round_state.pending_dora_count == 1

    def test_call_added_kan_maintains_dead_wall_size(self):
        round_state = self._create_round_state_with_pon()

        call_added_kan(round_state, seat=0, tile_id=3)

        # dead wall stays at 14 (one drawn, one replenished from live wall)
        assert len(round_state.dead_wall) == 14

    def test_call_added_kan_sets_rinshan_flag(self):
        round_state = self._create_round_state_with_pon()

        call_added_kan(round_state, seat=0, tile_id=3)

        assert round_state.players[0].is_rinshan is True

    def test_call_added_kan_raises_when_no_pon(self):
        round_state = self._create_round_state_with_pon()
        round_state.players[0].melds = []  # remove the pon

        with pytest.raises(ValueError, match="cannot call added kan"):
            call_added_kan(round_state, seat=0, tile_id=3)

    def test_call_added_kan_raises_when_tile_not_in_hand(self):
        round_state = self._create_round_state_with_pon()
        round_state.players[0].tiles = [36, 40, 44]  # no tile 3

        with pytest.raises(ValueError, match="cannot call added kan"):
            call_added_kan(round_state, seat=0, tile_id=3)


class TestCheckFourKans:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a basic round state."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[0, 1, 2, 3]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[4, 5, 6, 7]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[8, 9, 10, 11]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[12, 13, 14, 15]),
        ]
        return MahjongRoundState(players=players)

    def _create_kan_meld(self, tiles: list[int]) -> Meld:
        """Create a kan meld."""
        return Meld(meld_type=Meld.KAN, tiles=tiles, opened=True, who=0)

    def _create_shouminkan_meld(self, tiles: list[int]) -> Meld:
        """Create a shouminkan meld."""
        return Meld(meld_type=Meld.SHOUMINKAN, tiles=tiles, opened=True, who=0)

    def test_no_kans(self):
        round_state = self._create_round_state()

        result = check_four_kans(round_state)

        assert result is False

    def test_three_kans_different_players(self):
        round_state = self._create_round_state()
        round_state.players[0].melds = [self._create_kan_meld([0, 1, 2, 3])]
        round_state.players[1].melds = [self._create_kan_meld([4, 5, 6, 7])]
        round_state.players[2].melds = [self._create_kan_meld([8, 9, 10, 11])]

        result = check_four_kans(round_state)

        assert result is False

    def test_four_kans_by_different_players(self):
        round_state = self._create_round_state()
        round_state.players[0].melds = [self._create_kan_meld([0, 1, 2, 3])]
        round_state.players[1].melds = [self._create_kan_meld([4, 5, 6, 7])]
        round_state.players[2].melds = [self._create_kan_meld([8, 9, 10, 11])]
        round_state.players[3].melds = [self._create_kan_meld([12, 13, 14, 15])]

        result = check_four_kans(round_state)

        assert result is True

    def test_four_kans_by_two_players(self):
        round_state = self._create_round_state()
        round_state.players[0].melds = [
            self._create_kan_meld([0, 1, 2, 3]),
            self._create_kan_meld([36, 37, 38, 39]),
        ]
        round_state.players[1].melds = [
            self._create_kan_meld([4, 5, 6, 7]),
            self._create_kan_meld([40, 41, 42, 43]),
        ]

        result = check_four_kans(round_state)

        assert result is True

    def test_four_kans_by_one_player_no_abortive(self):
        # suukantsu is possible if one player has all 4 kans
        round_state = self._create_round_state()
        round_state.players[0].melds = [
            self._create_kan_meld([0, 1, 2, 3]),
            self._create_kan_meld([4, 5, 6, 7]),
            self._create_kan_meld([8, 9, 10, 11]),
            self._create_kan_meld([12, 13, 14, 15]),
        ]

        result = check_four_kans(round_state)

        # should NOT be abortive - one player can go for suukantsu
        assert result is False

    def test_mixed_kan_and_shouminkan(self):
        round_state = self._create_round_state()
        round_state.players[0].melds = [self._create_kan_meld([0, 1, 2, 3])]
        round_state.players[1].melds = [self._create_shouminkan_meld([4, 5, 6, 7])]
        round_state.players[2].melds = [self._create_kan_meld([8, 9, 10, 11])]
        round_state.players[3].melds = [self._create_shouminkan_meld([12, 13, 14, 15])]

        result = check_four_kans(round_state)

        assert result is True


class TestGetPossibleClosedKans:
    def _create_player(self, tiles: list[int], *, is_riichi: bool = False) -> MahjongPlayer:
        """Create a player with specified tiles."""
        return MahjongPlayer(seat=0, name="Test", tiles=tiles, is_riichi=is_riichi)

    def _create_round_state(self, player: MahjongPlayer, wall_count: int = 10) -> MahjongRoundState:
        """Create a round state with the given player and wall size."""
        players = [
            player,
            MahjongPlayer(seat=1, name="Bot1", is_bot=True),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True),
        ]
        return MahjongRoundState(players=players, wall=list(range(wall_count)))

    def test_no_possible_kans(self):
        player = self._create_player([0, 1, 2, 36, 40])
        round_state = self._create_round_state(player)

        result = get_possible_closed_kans(player, round_state)

        assert result == []

    def test_one_possible_kan(self):
        # player has all 4 copies of 1m (tiles 0-3)
        player = self._create_player([0, 1, 2, 3, 36, 40])
        round_state = self._create_round_state(player)

        result = get_possible_closed_kans(player, round_state)

        assert result == [0]  # tile_34 = 0 for 1m

    def test_multiple_possible_kans(self):
        # player has all 4 copies of 1m and 1p
        player = self._create_player([0, 1, 2, 3, 36, 37, 38, 39])
        round_state = self._create_round_state(player)

        result = get_possible_closed_kans(player, round_state)

        assert sorted(result) == [0, 9]  # tile_34 = 0 for 1m, 9 for 1p

    def test_no_kans_when_wall_too_small(self):
        player = self._create_player([0, 1, 2, 3])
        round_state = self._create_round_state(player, wall_count=1)

        result = get_possible_closed_kans(player, round_state)

        assert result == []

    def test_no_kans_when_max_kans_reached(self):
        player = self._create_player([0, 1, 2, 3, 36, 40])
        round_state = self._create_round_state(player)
        round_state.players[1].melds = [
            Meld(meld_type=Meld.KAN, tiles=[52, 53, 54, 55], opened=True, who=1),
            Meld(meld_type=Meld.KAN, tiles=[56, 57, 58, 59], opened=True, who=1),
        ]
        round_state.players[2].melds = [
            Meld(meld_type=Meld.KAN, tiles=[60, 61, 62, 63], opened=True, who=2),
            Meld(meld_type=Meld.KAN, tiles=[64, 65, 66, 67], opened=True, who=2),
        ]

        result = get_possible_closed_kans(player, round_state)

        assert result == []


class TestGetPossibleAddedKans:
    def _create_player_with_pon(self, hand_tiles: list[int], pon_tile_34: int) -> MahjongPlayer:
        """Create a player with a pon meld."""
        player = MahjongPlayer(seat=0, name="Test", tiles=hand_tiles)
        pon_tiles = [pon_tile_34 * 4, pon_tile_34 * 4 + 1, pon_tile_34 * 4 + 2]
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=pon_tiles,
            opened=True,
            called_tile=pon_tiles[2],
            who=0,
            from_who=1,
        )
        player.melds.append(pon_meld)
        return player

    def _create_round_state(self, player: MahjongPlayer, wall_count: int = 10) -> MahjongRoundState:
        """Create a round state with the given player and wall size."""
        players = [
            player,
            MahjongPlayer(seat=1, name="Bot1", is_bot=True),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True),
        ]
        return MahjongRoundState(players=players, wall=list(range(wall_count)))

    def test_no_possible_added_kans(self):
        player = MahjongPlayer(seat=0, name="Test", tiles=[36, 40, 44])
        round_state = self._create_round_state(player)

        result = get_possible_added_kans(player, round_state)

        assert result == []

    def test_one_possible_added_kan(self):
        # player has pon of 1m and 4th tile in hand
        player = self._create_player_with_pon([3, 36, 40], pon_tile_34=0)
        round_state = self._create_round_state(player)

        result = get_possible_added_kans(player, round_state)

        assert result == [0]

    def test_multiple_possible_added_kans(self):
        # player has two pons and both 4th tiles
        player = self._create_player_with_pon([3, 39, 44], pon_tile_34=0)
        # add another pon
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=[36, 37, 38],
            opened=True,
            called_tile=38,
            who=0,
            from_who=2,
        )
        player.melds.append(pon_meld)
        round_state = self._create_round_state(player)

        result = get_possible_added_kans(player, round_state)

        assert sorted(result) == [0, 9]

    def test_no_added_kans_when_in_riichi(self):
        player = self._create_player_with_pon([3, 36, 40], pon_tile_34=0)
        player.is_riichi = True
        round_state = self._create_round_state(player)

        result = get_possible_added_kans(player, round_state)

        assert result == []

    def test_no_added_kans_when_wall_too_small(self):
        player = self._create_player_with_pon([3, 36, 40], pon_tile_34=0)
        round_state = self._create_round_state(player, wall_count=1)

        result = get_possible_added_kans(player, round_state)

        assert result == []

    def test_no_added_kans_when_max_kans_reached(self):
        player = self._create_player_with_pon([3, 36, 40], pon_tile_34=0)
        round_state = self._create_round_state(player)
        round_state.players[1].melds = [
            Meld(meld_type=Meld.KAN, tiles=[52, 53, 54, 55], opened=True, who=1),
            Meld(meld_type=Meld.KAN, tiles=[56, 57, 58, 59], opened=True, who=1),
        ]
        round_state.players[2].melds = [
            Meld(meld_type=Meld.KAN, tiles=[60, 61, 62, 63], opened=True, who=2),
            Meld(meld_type=Meld.SHOUMINKAN, tiles=[64, 65, 66, 67], opened=True, who=2),
        ]

        result = get_possible_added_kans(player, round_state)

        assert result == []


class TestGetKuikaeTiles:
    def test_pon_kuikae_forbids_called_tile(self):
        # pon on 1m (tile_34=0) forbids discarding 1m
        result = get_kuikae_tiles(MeldCallType.PON, called_tile_34=0)

        assert result == [0]

    def test_pon_kuikae_honor_tile(self):
        # pon on East (tile_34=27) forbids discarding East
        result = get_kuikae_tiles(MeldCallType.PON, called_tile_34=27)

        assert result == [27]

    def test_chi_kuikae_called_tile_is_lowest(self):
        # chi: call 4m (tile_34=3) with 5m,6m in hand -> sequence 4-5-6
        # forbids 4m (called) and 7m (suji at other end, tile_34=6)
        result = get_kuikae_tiles(MeldCallType.CHI, called_tile_34=3, sequence_tiles_34=[4, 5])

        assert sorted(result) == [3, 6]

    def test_chi_kuikae_called_tile_is_highest(self):
        # chi: call 6m (tile_34=5) with 4m,5m in hand -> sequence 4-5-6
        # forbids 6m (called) and 3m (suji at other end, tile_34=2)
        result = get_kuikae_tiles(MeldCallType.CHI, called_tile_34=5, sequence_tiles_34=[3, 4])

        assert sorted(result) == [2, 5]

    def test_chi_kuikae_called_tile_is_middle(self):
        # chi: call 5m (tile_34=4) with 4m,6m in hand -> sequence 4-5-6
        # forbids only 5m (called), no suji for middle tile
        result = get_kuikae_tiles(MeldCallType.CHI, called_tile_34=4, sequence_tiles_34=[3, 5])

        assert result == [4]

    def test_chi_kuikae_no_suji_at_suit_boundary_low(self):
        # chi: call 3m (tile_34=2) with 1m,2m in hand -> sequence 1-2-3
        # called tile is highest, suji would be tile_34=0-1=-1, which is invalid
        # forbids only 3m
        result = get_kuikae_tiles(MeldCallType.CHI, called_tile_34=2, sequence_tiles_34=[0, 1])

        assert result == [2]

    def test_chi_kuikae_no_suji_at_suit_boundary_high(self):
        # chi: call 7m (tile_34=6) with 8m,9m in hand -> sequence 7-8-9
        # called tile is lowest, suji would be tile_34=8+1=9, but 9m is value 8 (max)
        # so suji would be tile_34=9 which is 1p (different suit), not valid
        result = get_kuikae_tiles(MeldCallType.CHI, called_tile_34=6, sequence_tiles_34=[7, 8])

        assert result == [6]

    def test_chi_kuikae_pin_suit(self):
        # chi in pin suit: call 4p (tile_34=12) with 5p,6p -> sequence 4-5-6p
        # forbids 4p (called) and 7p (tile_34=15)
        result = get_kuikae_tiles(MeldCallType.CHI, called_tile_34=12, sequence_tiles_34=[13, 14])

        assert sorted(result) == [12, 15]

    def test_chi_kuikae_sou_suit(self):
        # chi in sou suit: call 7s (tile_34=24) with 5s,6s -> sequence 5-6-7s
        # called tile is highest, forbids 7s and 4s (tile_34=21)
        result = get_kuikae_tiles(MeldCallType.CHI, called_tile_34=24, sequence_tiles_34=[22, 23])

        assert sorted(result) == [21, 24]


class TestCallPonSetsKuikae:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[0, 1, 36, 72]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[4, 5, 40, 76]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[8, 9, 44, 80]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[12, 13, 48, 84]),
        ]
        return MahjongRoundState(players=players, current_player_seat=1)

    def test_call_pon_sets_kuikae_tiles(self):
        round_state = self._create_round_state()

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        player = round_state.players[0]
        # pon on 1m (tile_34=0) should forbid discarding 1m
        assert player.kuikae_tiles == [0]


class TestCallChiSetsKuikae:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[0, 4, 36, 72]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[8, 12, 40, 76]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[16, 20, 44, 80]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[24, 28, 48, 84]),
        ]
        return MahjongRoundState(players=players, current_player_seat=0)

    def test_call_chi_sets_kuikae_tiles_called_lowest(self):
        round_state = self._create_round_state()
        # player 1 has 3m (8) and 4m (12), calls chi on 2m (4) from player 0
        # sequence: 2m-3m-4m, called tile is lowest (2m, tile_34=1)
        # suji: tile_34=3+1=4 (5m)

        call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=4, sequence_tiles=(8, 12))

        player = round_state.players[1]
        # forbids: 2m (tile_34=1) and 5m (tile_34=4)
        assert sorted(player.kuikae_tiles) == [1, 4]

    def test_call_chi_sets_kuikae_tiles_called_highest(self):
        round_state = self._create_round_state()
        # player 1 has 3m (8) and 4m (12), calls chi on 5m (16) from player 0
        round_state.players[0].tiles = [16, 36, 72, 108]
        round_state.players[1].tiles = [8, 12, 40, 76]
        # sequence: 3m-4m-5m, called tile is highest (5m, tile_34=4)
        # suji: tile_34=2-1=1 (2m)

        call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=16, sequence_tiles=(8, 12))

        player = round_state.players[1]
        # forbids: 5m (tile_34=4) and 2m (tile_34=1)
        assert sorted(player.kuikae_tiles) == [1, 4]

    def test_call_chi_sets_kuikae_tiles_called_middle(self):
        round_state = self._create_round_state()
        # player 1 has 3m (8) and 5m (16), calls chi on 4m (12) from player 0
        round_state.players[0].tiles = [12, 36, 72, 108]
        round_state.players[1].tiles = [8, 16, 40, 76]
        # sequence: 3m-4m-5m, called tile is middle (4m, tile_34=3)
        # no suji for middle position

        call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=12, sequence_tiles=(8, 16))

        player = round_state.players[1]
        # forbids: only 4m (tile_34=3)
        assert player.kuikae_tiles == [3]


class TestPaoDetection:
    """Tests for pao (liability) detection after pon/open kan calls."""

    def _create_round_state_with_dead_wall(self) -> MahjongRoundState:
        """Create a round state with proper dead wall setup."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[]),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True, tiles=[]),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True, tiles=[]),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True, tiles=[]),
        ]
        return MahjongRoundState(
            players=players,
            current_player_seat=1,
            wall=list(range(50)),
            dead_wall=[116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129],
            dora_indicators=[118],
        )

    def test_pao_triggers_on_third_dragon_pon(self):
        # player 0 already has pon of haku and hatsu, then pons chun from player 1
        # haku=31, hatsu=32, chun=33 (tile_34)
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        # existing 2 dragon pon melds
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=[124, 125, 126], opened=True, called_tile=126, who=0, from_who=2),
            Meld(meld_type=Meld.PON, tiles=[128, 129, 130], opened=True, called_tile=130, who=0, from_who=3),
        ]
        # player has 2 chun tiles in hand for the pon
        player.tiles = [132, 133, 36, 40, 44, 48, 72, 76, 80, 84]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=134)

        assert player.pao_seat == 1

    def test_pao_does_not_trigger_on_second_dragon_pon(self):
        # player 0 has pon of haku, then pons hatsu from player 1
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=[124, 125, 126], opened=True, called_tile=126, who=0, from_who=2),
        ]
        player.tiles = [128, 129, 36, 40, 44, 48, 72, 76, 80, 84]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=130)

        assert player.pao_seat is None

    def test_pao_triggers_on_fourth_wind_pon(self):
        # player 0 already has pon of E, S, W, then pons N from player 2
        # E=27, S=28, W=29, N=30 (tile_34)
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=[108, 109, 110], opened=True, called_tile=110, who=0, from_who=1),
            Meld(meld_type=Meld.PON, tiles=[112, 113, 114], opened=True, called_tile=114, who=0, from_who=3),
            Meld(meld_type=Meld.PON, tiles=[116, 117, 118], opened=True, called_tile=118, who=0, from_who=1),
        ]
        player.tiles = [120, 121, 36, 40, 44, 48, 72]

        call_pon(round_state, caller_seat=0, discarder_seat=2, tile_id=122)

        assert player.pao_seat == 2

    def test_pao_does_not_trigger_on_third_wind_pon(self):
        # player 0 has pon of E and S, then pons W from player 2
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=[108, 109, 110], opened=True, called_tile=110, who=0, from_who=1),
            Meld(meld_type=Meld.PON, tiles=[112, 113, 114], opened=True, called_tile=114, who=0, from_who=3),
        ]
        player.tiles = [116, 117, 36, 40, 44, 48, 72, 76, 80]

        call_pon(round_state, caller_seat=0, discarder_seat=2, tile_id=118)

        assert player.pao_seat is None

    def test_pao_triggers_on_third_dragon_open_kan(self):
        # player 0 has pon of haku and hatsu, then open kans chun from player 3
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=[124, 125, 126], opened=True, called_tile=126, who=0, from_who=2),
            Meld(meld_type=Meld.PON, tiles=[128, 129, 130], opened=True, called_tile=130, who=0, from_who=1),
        ]
        # player has 3 chun tiles in hand for the open kan
        player.tiles = [132, 133, 134, 36, 40, 44, 48, 72, 76, 80, 84, 88, 92]

        call_open_kan(round_state, caller_seat=0, discarder_seat=3, tile_id=135)

        assert player.pao_seat == 3

    def test_pao_not_triggered_for_non_dragon_non_wind_pon(self):
        # ponning a regular tile (e.g. 1m) does not trigger pao
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        player.tiles = [0, 1, 36, 40, 44, 48, 72, 76, 80, 84]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=2)

        assert player.pao_seat is None

    def test_pao_with_kan_dragon_melds(self):
        # player 0 has kan of haku and kan of hatsu, then pons chun
        # kan melds should count toward dragon set count
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        player.melds = [
            Meld(
                meld_type=Meld.KAN,
                tiles=[124, 125, 126, 127],
                opened=True,
                called_tile=127,
                who=0,
                from_who=2,
            ),
            Meld(
                meld_type=Meld.KAN,
                tiles=[128, 129, 130, 131],
                opened=True,
                called_tile=131,
                who=0,
                from_who=1,
            ),
        ]
        player.tiles = [132, 133, 36, 40, 44, 48, 72]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=134)

        assert player.pao_seat == 1

    def test_pao_with_shouminkan_dragon_melds(self):
        # player 0 has shouminkan of haku and pon of hatsu, then pons chun
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        player.melds = [
            Meld(
                meld_type=Meld.SHOUMINKAN,
                tiles=[124, 125, 126, 127],
                opened=True,
                called_tile=126,
                who=0,
                from_who=2,
            ),
            Meld(meld_type=Meld.PON, tiles=[128, 129, 130], opened=True, called_tile=130, who=0, from_who=1),
        ]
        player.tiles = [132, 133, 36, 40, 44, 48, 72, 76, 80]

        call_pon(round_state, caller_seat=0, discarder_seat=3, tile_id=134)

        assert player.pao_seat == 3
