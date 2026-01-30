"""
Unit tests for chi meld operations, kuikae tile computation, and chi kuikae.
"""

import pytest
from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.enums import MeldCallType
from game.logic.melds import (
    call_chi,
    can_call_chi,
    get_kuikae_tiles,
)
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.tests.unit.helpers import _string_to_34_tile, _string_to_34_tiles


class TestCanCallChi:
    def _create_player(self, tiles: list[int], *, is_riichi: bool = False) -> MahjongPlayer:
        """Create a player with specified tiles."""
        return MahjongPlayer(seat=1, name="Test", tiles=tiles, is_riichi=is_riichi)

    def test_can_call_chi_lowest_in_sequence(self):
        # player has 2m and 3m, can chi a discarded 1m
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        player = self._create_player([man_2m, man_3m, *TilesConverter.string_to_136_array(pin="1", sou="1")])

        # someone at seat 0 discards 1m, caller at seat 1 is kamicha
        result = can_call_chi(player, discarded_tile=man_1m, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (man_2m, man_3m)

    def test_can_call_chi_middle_in_sequence(self):
        # player has 1m and 3m, can chi a discarded 2m
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        player = self._create_player([man_1m, man_3m, *TilesConverter.string_to_136_array(pin="1", sou="1")])

        # discarder at seat 0, caller at seat 1
        result = can_call_chi(player, discarded_tile=man_2m, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (man_1m, man_3m)

    def test_can_call_chi_highest_in_sequence(self):
        # player has 7m and 8m, can chi a discarded 9m
        man_7m = TilesConverter.string_to_136_array(man="7")[0]
        man_8m = TilesConverter.string_to_136_array(man="8")[0]
        man_9m = TilesConverter.string_to_136_array(man="9")[0]
        player = self._create_player([man_7m, man_8m, *TilesConverter.string_to_136_array(pin="1", sou="1")])

        result = can_call_chi(player, discarded_tile=man_9m, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (man_7m, man_8m)

    def test_can_call_chi_multiple_combinations(self):
        # player has 3m, 4m, 6m, can chi a discarded 5m
        # possible: 3m+4m (345), 4m+6m (456)
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]
        man_5m = TilesConverter.string_to_136_array(man="5")[0]
        man_6m = TilesConverter.string_to_136_array(man="6")[0]
        player = self._create_player([man_3m, man_4m, man_6m, *TilesConverter.string_to_136_array(sou="1")])

        result = can_call_chi(player, discarded_tile=man_5m, discarder_seat=0, caller_seat=1)

        assert len(result) == 2
        # check both combinations exist
        combinations = set(result)
        assert (man_3m, man_4m) in combinations  # 3m+4m for 345
        assert (man_4m, man_6m) in combinations  # 4m+6m for 456

    def test_can_call_chi_three_combinations(self):
        # player has 4m, 6m, 7m to form 456 or 567 with discarded 5m
        man_4m = TilesConverter.string_to_136_array(man="4")[0]
        man_5m = TilesConverter.string_to_136_array(man="5")[0]
        man_6m = TilesConverter.string_to_136_array(man="6")[0]
        man_7m = TilesConverter.string_to_136_array(man="7")[0]
        player = self._create_player([man_4m, man_6m, man_7m, *TilesConverter.string_to_136_array(sou="1")])

        result = can_call_chi(player, discarded_tile=man_5m, discarder_seat=0, caller_seat=1)

        assert len(result) == 2
        combinations = set(result)
        assert (man_4m, man_6m) in combinations  # 4m+6m for 456
        assert (man_6m, man_7m) in combinations  # 6m+7m for 567

    def test_cannot_call_chi_not_kamicha(self):
        # player has tiles to form chi but is not to the left
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        player = self._create_player([man_2m, man_3m, *TilesConverter.string_to_136_array(pin="1", sou="1")])

        # discarder at seat 0, caller at seat 2 (not kamicha)
        result = can_call_chi(player, discarded_tile=man_1m, discarder_seat=0, caller_seat=2)

        assert result == []

    def test_cannot_call_chi_honor_tiles(self):
        # player has East tiles but cannot chi honors
        east = TilesConverter.string_to_136_array(honors="111")
        player = self._create_player(
            [east[0], east[1], *TilesConverter.string_to_136_array(pin="1", sou="1")]
        )

        result = can_call_chi(player, discarded_tile=east[2], discarder_seat=0, caller_seat=1)

        assert result == []

    def test_cannot_call_chi_when_in_riichi(self):
        # player has tiles to form chi but is in riichi
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        player = self._create_player(
            [man_2m, man_3m, *TilesConverter.string_to_136_array(pin="1", sou="1")],
            is_riichi=True,
        )

        result = can_call_chi(player, discarded_tile=man_1m, discarder_seat=0, caller_seat=1)

        assert result == []

    def test_cannot_call_chi_missing_tiles(self):
        # player doesn't have the needed tiles
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        player = self._create_player(
            TilesConverter.string_to_136_array(man="2", pin="1", sou="1", honors="1")
        )

        result = can_call_chi(player, discarded_tile=man_1m, discarder_seat=0, caller_seat=1)

        assert result == []

    def test_can_call_chi_pin_suit(self):
        # test chi with pin (circles) suit
        pin_1p = TilesConverter.string_to_136_array(pin="1")[0]
        pin_2p = TilesConverter.string_to_136_array(pin="2")[0]
        pin_3p = TilesConverter.string_to_136_array(pin="3")[0]
        player = self._create_player([pin_2p, pin_3p, *TilesConverter.string_to_136_array(man="1", sou="1")])

        result = can_call_chi(player, discarded_tile=pin_1p, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (pin_2p, pin_3p)

    def test_can_call_chi_sou_suit(self):
        # test chi with sou (bamboo) suit
        sou_7s = TilesConverter.string_to_136_array(sou="7")[0]
        sou_8s = TilesConverter.string_to_136_array(sou="8")[0]
        sou_9s = TilesConverter.string_to_136_array(sou="9")[0]
        player = self._create_player([sou_7s, sou_8s, *TilesConverter.string_to_136_array(man="1", pin="1")])

        result = can_call_chi(player, discarded_tile=sou_9s, discarder_seat=0, caller_seat=1)

        assert len(result) == 1
        assert result[0] == (sou_7s, sou_8s)

    def test_can_call_chi_seat_wraparound(self):
        # test kamicha calculation with seat wraparound
        # discarder at seat 3, caller at seat 0 (0 = (3+1)%4)
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        player = MahjongPlayer(
            seat=0,
            name="Test",
            tiles=[man_2m, man_3m, *TilesConverter.string_to_136_array(pin="1", sou="1")],
        )

        result = can_call_chi(player, discarded_tile=man_1m, discarder_seat=3, caller_seat=0)

        assert len(result) == 1

    def test_cannot_call_chi_wrong_suit(self):
        # player has tiles from different suit than discarded
        # has 2p, 3p but discarded is 1m
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        player = self._create_player(TilesConverter.string_to_136_array(pin="23", sou="1", honors="1"))

        result = can_call_chi(player, discarded_tile=man_1m, discarder_seat=0, caller_seat=1)

        assert result == []

    def test_can_call_chi_edge_case_1m(self):
        # 1m can only be in sequences 123
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        player = self._create_player([man_2m, man_3m, *TilesConverter.string_to_136_array(pin="1", sou="1")])

        # can form 123
        result = can_call_chi(player, discarded_tile=man_1m, discarder_seat=0, caller_seat=1)
        assert len(result) == 1

    def test_can_call_chi_edge_case_9m(self):
        # 9m can only be in sequences 789
        man_7m = TilesConverter.string_to_136_array(man="7")[0]
        man_8m = TilesConverter.string_to_136_array(man="8")[0]
        man_9m = TilesConverter.string_to_136_array(man="9")[0]
        player = self._create_player([man_7m, man_8m, *TilesConverter.string_to_136_array(pin="1", sou="1")])

        # can form 789
        result = can_call_chi(player, discarded_tile=man_9m, discarder_seat=0, caller_seat=1)
        assert len(result) == 1


class TestCallChi:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing."""
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]
        man_5m = TilesConverter.string_to_136_array(man="5")[0]
        man_6m = TilesConverter.string_to_136_array(man="6")[0]
        man_7m = TilesConverter.string_to_136_array(man="7")[0]
        man_8m = TilesConverter.string_to_136_array(man="8")[0]
        players = [
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=[man_1m, man_2m, *TilesConverter.string_to_136_array(pin="1", sou="1")],
            ),
            MahjongPlayer(
                seat=1,
                name="Bot1",
                tiles=[man_3m, man_4m, *TilesConverter.string_to_136_array(pin="2", sou="2")],
            ),
            MahjongPlayer(
                seat=2,
                name="Bot2",
                tiles=[man_5m, man_6m, *TilesConverter.string_to_136_array(pin="3", sou="3")],
            ),
            MahjongPlayer(
                seat=3,
                name="Bot3",
                tiles=[man_7m, man_8m, *TilesConverter.string_to_136_array(pin="4", sou="4")],
            ),
        ]
        return MahjongRoundState(players=players, current_player_seat=0)

    def test_call_chi_removes_tiles_from_hand(self):
        round_state = self._create_round_state()
        # player 1 has 3m and 4m, calls chi on 2m from player 0
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]
        pin_2p = TilesConverter.string_to_136_array(pin="2")[0]
        sou_2s = TilesConverter.string_to_136_array(sou="2")[0]

        call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_3m, man_4m)
        )

        player = round_state.players[1]
        # should have removed 3m and 4m
        assert len(player.tiles) == 2
        assert pin_2p in player.tiles
        assert sou_2s in player.tiles

    def test_call_chi_creates_meld(self):
        round_state = self._create_round_state()
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]

        meld = call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_3m, man_4m)
        )

        assert meld.type == Meld.CHI
        assert meld.opened is True
        assert meld.called_tile == man_2m
        assert meld.who == 1
        assert meld.from_who == 0
        # meld tiles should be sorted and contain all 3 tiles
        assert sorted(meld.tiles) == sorted([man_2m, man_3m, man_4m])

    def test_call_chi_adds_meld_to_player(self):
        round_state = self._create_round_state()
        player = round_state.players[1]
        assert len(player.melds) == 0
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]

        call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_3m, man_4m)
        )

        assert len(player.melds) == 1
        assert player.melds[0].type == Meld.CHI

    def test_call_chi_adds_to_open_hands(self):
        round_state = self._create_round_state()
        assert round_state.players_with_open_hands == []
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]

        call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_3m, man_4m)
        )

        assert 1 in round_state.players_with_open_hands

    def test_call_chi_does_not_duplicate_open_hands(self):
        round_state = self._create_round_state()
        round_state.players_with_open_hands = [1]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]

        call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_3m, man_4m)
        )

        assert round_state.players_with_open_hands == [1]

    def test_call_chi_clears_ippatsu(self):
        round_state = self._create_round_state()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True
        round_state.players[2].is_ippatsu = True
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]

        call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_3m, man_4m)
        )

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_chi_sets_current_player_to_caller(self):
        round_state = self._create_round_state()
        assert round_state.current_player_seat == 0
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]

        call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_3m, man_4m)
        )

        assert round_state.current_player_seat == 1

    def test_call_chi_returns_meld(self):
        round_state = self._create_round_state()
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]

        result = call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_3m, man_4m)
        )

        assert isinstance(result, Meld)

    def test_call_chi_with_wraparound_seat(self):
        round_state = self._create_round_state()
        # player 0 calls chi on tile from player 3 (seat wraparound case)
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        round_state.players[0].tiles = [man_2m, man_3m, *TilesConverter.string_to_136_array(pin="1", sou="1")]
        round_state.current_player_seat = 3

        meld = call_chi(
            round_state, caller_seat=0, discarder_seat=3, tile_id=man_1m, sequence_tiles=(man_2m, man_3m)
        )

        assert meld.from_who == 3
        assert meld.who == 0
        assert round_state.current_player_seat == 0

    def test_call_chi_raises_when_tile_not_in_hand(self):
        round_state = self._create_round_state()
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]

        with pytest.raises(ValueError, match="not in list"):
            call_chi(
                round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_1m, man_2m)
            )


class TestGetKuikaeTiles:
    def test_pon_kuikae_forbids_called_tile(self):
        # pon on 1m (tile_34=0) forbids discarding 1m
        result = get_kuikae_tiles(MeldCallType.PON, called_tile_34=_string_to_34_tile(man="1"))

        assert result == _string_to_34_tiles(man="1")

    def test_pon_kuikae_honor_tile(self):
        # pon on East (tile_34=27) forbids discarding East
        result = get_kuikae_tiles(MeldCallType.PON, called_tile_34=_string_to_34_tile(honors="1"))

        assert result == _string_to_34_tiles(honors="1")

    def test_chi_kuikae_called_tile_is_lowest(self):
        # chi: call 4m (tile_34=3) with 5m,6m in hand -> sequence 4-5-6
        # forbids 4m (called) and 7m (suji at other end, tile_34=6)
        result = get_kuikae_tiles(
            MeldCallType.CHI,
            called_tile_34=_string_to_34_tile(man="4"),
            sequence_tiles_34=_string_to_34_tiles(man="56"),
        )

        assert sorted(result) == _string_to_34_tiles(man="47")

    def test_chi_kuikae_called_tile_is_highest(self):
        # chi: call 6m (tile_34=5) with 4m,5m in hand -> sequence 4-5-6
        # forbids 6m (called) and 3m (suji at other end, tile_34=2)
        result = get_kuikae_tiles(
            MeldCallType.CHI,
            called_tile_34=_string_to_34_tile(man="6"),
            sequence_tiles_34=_string_to_34_tiles(man="45"),
        )

        assert sorted(result) == _string_to_34_tiles(man="36")

    def test_chi_kuikae_called_tile_is_middle(self):
        # chi: call 5m (tile_34=4) with 4m,6m in hand -> sequence 4-5-6
        # forbids only 5m (called), no suji for middle tile
        result = get_kuikae_tiles(
            MeldCallType.CHI,
            called_tile_34=_string_to_34_tile(man="5"),
            sequence_tiles_34=_string_to_34_tiles(man="46"),
        )

        assert result == _string_to_34_tiles(man="5")

    def test_chi_kuikae_no_suji_at_suit_boundary_low(self):
        # chi: call 3m (tile_34=2) with 1m,2m in hand -> sequence 1-2-3
        # called tile is highest, suji would be tile_34=0-1=-1, which is invalid
        # forbids only 3m
        result = get_kuikae_tiles(
            MeldCallType.CHI,
            called_tile_34=_string_to_34_tile(man="3"),
            sequence_tiles_34=_string_to_34_tiles(man="12"),
        )

        assert result == _string_to_34_tiles(man="3")

    def test_chi_kuikae_no_suji_at_suit_boundary_high(self):
        # chi: call 7m (tile_34=6) with 8m,9m in hand -> sequence 7-8-9
        # called tile is lowest, suji would be tile_34=8+1=9, but 9m is value 8 (max)
        # so suji would be tile_34=9 which is 1p (different suit), not valid
        result = get_kuikae_tiles(
            MeldCallType.CHI,
            called_tile_34=_string_to_34_tile(man="7"),
            sequence_tiles_34=_string_to_34_tiles(man="89"),
        )

        assert result == _string_to_34_tiles(man="7")

    def test_chi_kuikae_pin_suit(self):
        # chi in pin suit: call 4p (tile_34=12) with 5p,6p -> sequence 4-5-6p
        # forbids 4p (called) and 7p (tile_34=15)
        result = get_kuikae_tiles(
            MeldCallType.CHI,
            called_tile_34=_string_to_34_tile(pin="4"),
            sequence_tiles_34=_string_to_34_tiles(pin="56"),
        )

        assert sorted(result) == _string_to_34_tiles(pin="47")

    def test_chi_kuikae_sou_suit(self):
        # chi in sou suit: call 7s (tile_34=24) with 5s,6s -> sequence 5-6-7s
        # called tile is highest, forbids 7s and 4s (tile_34=21)
        result = get_kuikae_tiles(
            MeldCallType.CHI,
            called_tile_34=_string_to_34_tile(sou="7"),
            sequence_tiles_34=_string_to_34_tiles(sou="56"),
        )

        assert sorted(result) == _string_to_34_tiles(sou="47")


class TestCallChiSetsKuikae:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing."""
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]
        man_5m = TilesConverter.string_to_136_array(man="5")[0]
        man_6m = TilesConverter.string_to_136_array(man="6")[0]
        man_7m = TilesConverter.string_to_136_array(man="7")[0]
        man_8m = TilesConverter.string_to_136_array(man="8")[0]
        players = [
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=[man_1m, man_2m, *TilesConverter.string_to_136_array(pin="1", sou="1")],
            ),
            MahjongPlayer(
                seat=1,
                name="Bot1",
                tiles=[man_3m, man_4m, *TilesConverter.string_to_136_array(pin="2", sou="2")],
            ),
            MahjongPlayer(
                seat=2,
                name="Bot2",
                tiles=[man_5m, man_6m, *TilesConverter.string_to_136_array(pin="3", sou="3")],
            ),
            MahjongPlayer(
                seat=3,
                name="Bot3",
                tiles=[man_7m, man_8m, *TilesConverter.string_to_136_array(pin="4", sou="4")],
            ),
        ]
        return MahjongRoundState(players=players, current_player_seat=0)

    def test_call_chi_sets_kuikae_tiles_called_lowest(self):
        round_state = self._create_round_state()
        # player 1 has 3m and 4m, calls chi on 2m from player 0
        # sequence: 2m-3m-4m, called tile is lowest (2m, tile_34=1)
        # suji: tile_34=3+1=4 (5m)
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]

        call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_2m, sequence_tiles=(man_3m, man_4m)
        )

        player = round_state.players[1]
        # forbids: 2m (tile_34=1) and 5m (tile_34=4)
        assert sorted(player.kuikae_tiles) == _string_to_34_tiles(man="25")

    def test_call_chi_sets_kuikae_tiles_called_highest(self):
        round_state = self._create_round_state()
        # player 1 has 3m and 4m, calls chi on 5m from player 0
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]
        man_5m = TilesConverter.string_to_136_array(man="5")[0]
        round_state.players[0].tiles = [
            man_5m,
            *TilesConverter.string_to_136_array(pin="1", sou="1", honors="1"),
        ]
        round_state.players[1].tiles = [
            man_3m,
            man_4m,
            *TilesConverter.string_to_136_array(pin="2", sou="2"),
        ]
        # sequence: 3m-4m-5m, called tile is highest (5m, tile_34=4)
        # suji: tile_34=2-1=1 (2m)

        call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_5m, sequence_tiles=(man_3m, man_4m)
        )

        player = round_state.players[1]
        # forbids: 5m (tile_34=4) and 2m (tile_34=1)
        assert sorted(player.kuikae_tiles) == _string_to_34_tiles(man="25")

    def test_call_chi_sets_kuikae_tiles_called_middle(self):
        round_state = self._create_round_state()
        # player 1 has 3m and 5m, calls chi on 4m from player 0
        man_3m = TilesConverter.string_to_136_array(man="3")[0]
        man_4m = TilesConverter.string_to_136_array(man="4")[0]
        man_5m = TilesConverter.string_to_136_array(man="5")[0]
        round_state.players[0].tiles = [
            man_4m,
            *TilesConverter.string_to_136_array(pin="1", sou="1", honors="1"),
        ]
        round_state.players[1].tiles = [
            man_3m,
            man_5m,
            *TilesConverter.string_to_136_array(pin="2", sou="2"),
        ]
        # sequence: 3m-4m-5m, called tile is middle (4m, tile_34=3)
        # no suji for middle position

        call_chi(
            round_state, caller_seat=1, discarder_seat=0, tile_id=man_4m, sequence_tiles=(man_3m, man_5m)
        )

        player = round_state.players[1]
        # forbids: only 4m (tile_34=3)
        assert player.kuikae_tiles == _string_to_34_tiles(man="4")
