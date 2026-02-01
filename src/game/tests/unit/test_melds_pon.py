"""
Unit tests for pon meld operations, pon kuikae, and pao detection.
"""

import pytest
from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.melds import (
    call_open_kan,
    call_pon,
    can_call_pon,
)
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.tests.unit.helpers import _string_to_34_tiles


class TestCanCallPon:
    def _create_player(self, tiles: list[int], *, is_riichi: bool = False) -> MahjongPlayer:
        """Create a player with specified tiles."""
        return MahjongPlayer(seat=0, name="Test", tiles=tiles, is_riichi=is_riichi)

    def test_can_call_pon_with_two_matching_tiles(self):
        # player has 1m 1m in hand
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player(
            [man_1m[0], man_1m[1], *TilesConverter.string_to_136_array(pin="1", sou="1")]
        )

        # someone discards 1m
        result = can_call_pon(player, discarded_tile=man_1m[2])

        assert result is True

    def test_can_call_pon_with_three_matching_tiles(self):
        # player has 1m 1m 1m in hand
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player(
            [man_1m[0], man_1m[1], man_1m[2], *TilesConverter.string_to_136_array(pin="1")]
        )

        result = can_call_pon(player, discarded_tile=man_1m[3])

        assert result is True

    def test_cannot_call_pon_with_one_matching_tile(self):
        # player has only one 1m
        man_1m = TilesConverter.string_to_136_array(man="11")
        player = self._create_player(
            [man_1m[0], *TilesConverter.string_to_136_array(pin="1", sou="1", honors="1")]
        )

        result = can_call_pon(player, discarded_tile=man_1m[1])

        assert result is False

    def test_cannot_call_pon_with_no_matching_tiles(self):
        # player has no 1m tiles
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        player = self._create_player(
            TilesConverter.string_to_136_array(pin="1", sou="1", honors="1", man="2")
        )

        result = can_call_pon(player, discarded_tile=man_1m)

        assert result is False

    def test_cannot_call_pon_when_in_riichi(self):
        # player has matching tiles but is in riichi
        man_1m = TilesConverter.string_to_136_array(man="111")
        player = self._create_player(
            [man_1m[0], man_1m[1], *TilesConverter.string_to_136_array(pin="1", sou="1")],
            is_riichi=True,
        )

        result = can_call_pon(player, discarded_tile=man_1m[2])

        assert result is False

    def test_can_call_pon_different_tile_copies(self):
        # player has tiles 0 and 2 (both 1m, different copies)
        man_1m = TilesConverter.string_to_136_array(man="111")
        player = self._create_player(
            [man_1m[0], man_1m[2], *TilesConverter.string_to_136_array(pin="1", sou="1")]
        )

        result = can_call_pon(player, discarded_tile=man_1m[1])

        assert result is True

    def test_can_call_pon_honor_tiles(self):
        # player has East wind tiles
        east = TilesConverter.string_to_136_array(honors="111")
        player = self._create_player(
            [east[0], east[1], *TilesConverter.string_to_136_array(pin="1", sou="1")]
        )

        # someone discards East
        result = can_call_pon(player, discarded_tile=east[2])

        assert result is True


class TestCallPon:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing."""
        man_1m = TilesConverter.string_to_136_array(man="11")
        man_2m = TilesConverter.string_to_136_array(man="22")
        man_3m = TilesConverter.string_to_136_array(man="33")
        man_4m = TilesConverter.string_to_136_array(man="44")
        players = [
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=man_1m + TilesConverter.string_to_136_array(pin="1", sou="1"),
            ),
            MahjongPlayer(
                seat=1,
                name="Bot1",
                tiles=man_2m + TilesConverter.string_to_136_array(pin="2", sou="2"),
            ),
            MahjongPlayer(
                seat=2,
                name="Bot2",
                tiles=man_3m + TilesConverter.string_to_136_array(pin="3", sou="3"),
            ),
            MahjongPlayer(
                seat=3,
                name="Bot3",
                tiles=man_4m + TilesConverter.string_to_136_array(pin="4", sou="4"),
            ),
        ]
        return MahjongRoundState(players=players, current_player_seat=1)

    def test_call_pon_removes_tiles_from_hand(self):
        round_state = self._create_round_state()
        # player 0 calls pon on 1m discarded by player 1
        # player 0 has two 1m tiles
        man_1m = TilesConverter.string_to_136_array(man="111")
        pin_1p = TilesConverter.string_to_136_array(pin="1")[0]
        sou_1s = TilesConverter.string_to_136_array(sou="1")[0]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        player = round_state.players[0]
        # should have removed the two 1m tiles
        assert len(player.tiles) == 2
        assert pin_1p in player.tiles
        assert sou_1s in player.tiles

    def test_call_pon_creates_meld(self):
        round_state = self._create_round_state()
        man_1m = TilesConverter.string_to_136_array(man="111")

        meld = call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        assert meld.type == Meld.PON
        assert meld.opened is True
        assert meld.called_tile == man_1m[2]
        assert meld.who == 0
        assert meld.from_who == 1
        # meld tiles should be sorted and contain all 3 tiles
        assert meld.tiles is not None
        assert sorted(meld.tiles) == sorted(man_1m)

    def test_call_pon_adds_meld_to_player(self):
        round_state = self._create_round_state()
        player = round_state.players[0]
        assert len(player.melds) == 0
        man_1m = TilesConverter.string_to_136_array(man="111")

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        assert len(player.melds) == 1
        assert player.melds[0].type == Meld.PON

    def test_call_pon_adds_to_open_hands(self):
        round_state = self._create_round_state()
        assert round_state.players_with_open_hands == []
        man_1m = TilesConverter.string_to_136_array(man="111")

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        assert 0 in round_state.players_with_open_hands

    def test_call_pon_does_not_duplicate_open_hands(self):
        round_state = self._create_round_state()
        round_state.players_with_open_hands = [0]
        man_1m = TilesConverter.string_to_136_array(man="111")

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        assert round_state.players_with_open_hands == [0]

    def test_call_pon_clears_ippatsu(self):
        round_state = self._create_round_state()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True
        round_state.players[2].is_ippatsu = True
        man_1m = TilesConverter.string_to_136_array(man="111")

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_pon_sets_current_player_to_caller(self):
        round_state = self._create_round_state()
        assert round_state.current_player_seat == 1
        man_1m = TilesConverter.string_to_136_array(man="111")

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        assert round_state.current_player_seat == 0

    def test_call_pon_returns_meld(self):
        round_state = self._create_round_state()
        man_1m = TilesConverter.string_to_136_array(man="111")

        result = call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        assert isinstance(result, Meld)

    def test_call_pon_raises_when_not_enough_tiles(self):
        round_state = self._create_round_state()
        # player 0 only has one 1m tile
        man_1m = TilesConverter.string_to_136_array(man="111")
        round_state.players[0].tiles = [
            man_1m[0],
            *TilesConverter.string_to_136_array(pin="1", sou="1", honors="1"),
        ]

        with pytest.raises(ValueError, match="cannot call pon"):
            call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

    def test_call_pon_from_any_player(self):
        round_state = self._create_round_state()
        # player 2 calls pon on tile discarded by player 0
        man_1m = TilesConverter.string_to_136_array(man="111")
        round_state.players[2].tiles = [
            man_1m[0],
            man_1m[1],
            *TilesConverter.string_to_136_array(pin="3", sou="3"),
        ]
        round_state.current_player_seat = 0

        meld = call_pon(round_state, caller_seat=2, discarder_seat=0, tile_id=man_1m[2])

        assert meld.from_who == 0
        assert meld.who == 2
        assert round_state.current_player_seat == 2

    def test_call_pon_selects_correct_tiles_when_multiple_copies(self):
        round_state = self._create_round_state()
        # player has three 1m tiles (0, 1, 3) and one other
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_1p = TilesConverter.string_to_136_array(pin="1")[0]
        round_state.players[0].tiles = [man_1m[0], man_1m[1], man_1m[3], pin_1p]

        meld = call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        # should remove first 2 matching tiles found (man_1m[0] and man_1m[1])
        player = round_state.players[0]
        assert len(player.tiles) == 2
        # remaining should be the third 1m and the 1p
        assert man_1m[3] in player.tiles
        assert pin_1p in player.tiles
        # meld should have man_1m[0], man_1m[1], and the called tile man_1m[2]
        assert meld.tiles is not None
        assert sorted(meld.tiles) == sorted([man_1m[0], man_1m[1], man_1m[2]])


class TestCallPonSetsKuikae:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing."""
        man_1m = TilesConverter.string_to_136_array(man="11")
        man_2m = TilesConverter.string_to_136_array(man="22")
        man_3m = TilesConverter.string_to_136_array(man="33")
        man_4m = TilesConverter.string_to_136_array(man="44")
        players = [
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=man_1m + TilesConverter.string_to_136_array(pin="1", sou="1"),
            ),
            MahjongPlayer(
                seat=1,
                name="Bot1",
                tiles=man_2m + TilesConverter.string_to_136_array(pin="2", sou="2"),
            ),
            MahjongPlayer(
                seat=2,
                name="Bot2",
                tiles=man_3m + TilesConverter.string_to_136_array(pin="3", sou="3"),
            ),
            MahjongPlayer(
                seat=3,
                name="Bot3",
                tiles=man_4m + TilesConverter.string_to_136_array(pin="4", sou="4"),
            ),
        ]
        return MahjongRoundState(players=players, current_player_seat=1)

    def test_call_pon_sets_kuikae_tiles(self):
        round_state = self._create_round_state()
        man_1m = TilesConverter.string_to_136_array(man="111")

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        player = round_state.players[0]
        # pon on 1m (tile_34=0) should forbid discarding 1m
        assert player.kuikae_tiles == _string_to_34_tiles(man="1")


class TestPaoDetection:
    """Tests for pao (liability) detection after pon/open kan calls."""

    def _create_round_state_with_dead_wall(self) -> MahjongRoundState:
        """Create a round state with proper dead wall setup."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[]),
            MahjongPlayer(seat=1, name="Bot1", tiles=[]),
            MahjongPlayer(seat=2, name="Bot2", tiles=[]),
            MahjongPlayer(seat=3, name="Bot3", tiles=[]),
        ]
        west = TilesConverter.string_to_136_array(honors="3333")
        north = TilesConverter.string_to_136_array(honors="4444")
        haku = TilesConverter.string_to_136_array(honors="5555")
        hatsu = TilesConverter.string_to_136_array(honors="66")
        return MahjongRoundState(
            players=players,
            current_player_seat=1,
            wall=list(range(50)),
            dead_wall=west + north + haku + hatsu,
            dora_indicators=[west[2]],
        )

    def test_pao_triggers_on_third_dragon_pon(self):
        # player 0 already has pon of haku and hatsu, then pons chun from player 1
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        haku = TilesConverter.string_to_136_array(honors="555")
        hatsu = TilesConverter.string_to_136_array(honors="666")
        chun = TilesConverter.string_to_136_array(honors="7777")
        # existing 2 dragon pon melds
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=haku, opened=True, called_tile=haku[2], who=0, from_who=2),
            Meld(meld_type=Meld.PON, tiles=hatsu, opened=True, called_tile=hatsu[2], who=0, from_who=3),
        ]
        # player has 2 chun tiles in hand for the pon
        player.tiles = [chun[0], chun[1], *TilesConverter.string_to_136_array(pin="1234", sou="1234")]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=chun[2])

        assert player.pao_seat == 1

    def test_pao_does_not_trigger_on_second_dragon_pon(self):
        # player 0 has pon of haku, then pons hatsu from player 1
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        haku = TilesConverter.string_to_136_array(honors="555")
        hatsu = TilesConverter.string_to_136_array(honors="666")
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=haku, opened=True, called_tile=haku[2], who=0, from_who=2),
        ]
        player.tiles = [hatsu[0], hatsu[1], *TilesConverter.string_to_136_array(pin="1234", sou="1234")]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=hatsu[2])

        assert player.pao_seat is None

    def test_pao_triggers_on_fourth_wind_pon(self):
        # player 0 already has pon of E, S, W, then pons N from player 2
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        east = TilesConverter.string_to_136_array(honors="111")
        south = TilesConverter.string_to_136_array(honors="222")
        west = TilesConverter.string_to_136_array(honors="333")
        north = TilesConverter.string_to_136_array(honors="444")
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=east, opened=True, called_tile=east[2], who=0, from_who=1),
            Meld(meld_type=Meld.PON, tiles=south, opened=True, called_tile=south[2], who=0, from_who=3),
            Meld(meld_type=Meld.PON, tiles=west, opened=True, called_tile=west[2], who=0, from_who=1),
        ]
        player.tiles = [north[0], north[1], *TilesConverter.string_to_136_array(pin="1234", sou="1")]

        call_pon(round_state, caller_seat=0, discarder_seat=2, tile_id=north[2])

        assert player.pao_seat == 2

    def test_pao_does_not_trigger_on_third_wind_pon(self):
        # player 0 has pon of E and S, then pons W from player 2
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        east = TilesConverter.string_to_136_array(honors="111")
        south = TilesConverter.string_to_136_array(honors="222")
        west = TilesConverter.string_to_136_array(honors="333")
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=east, opened=True, called_tile=east[2], who=0, from_who=1),
            Meld(meld_type=Meld.PON, tiles=south, opened=True, called_tile=south[2], who=0, from_who=3),
        ]
        player.tiles = [west[0], west[1], *TilesConverter.string_to_136_array(pin="1234", sou="123")]

        call_pon(round_state, caller_seat=0, discarder_seat=2, tile_id=west[2])

        assert player.pao_seat is None

    def test_pao_triggers_on_third_dragon_open_kan(self):
        # player 0 has pon of haku and hatsu, then open kans chun from player 3
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        haku = TilesConverter.string_to_136_array(honors="555")
        hatsu = TilesConverter.string_to_136_array(honors="666")
        chun = TilesConverter.string_to_136_array(honors="7777")
        player.melds = [
            Meld(meld_type=Meld.PON, tiles=haku, opened=True, called_tile=haku[2], who=0, from_who=2),
            Meld(meld_type=Meld.PON, tiles=hatsu, opened=True, called_tile=hatsu[2], who=0, from_who=1),
        ]
        # player has 3 chun tiles in hand for the open kan
        player.tiles = [
            chun[0],
            chun[1],
            chun[2],
            *TilesConverter.string_to_136_array(pin="1234", sou="1234567"),
        ]

        call_open_kan(round_state, caller_seat=0, discarder_seat=3, tile_id=chun[3])

        assert player.pao_seat == 3

    def test_pao_not_triggered_for_non_dragon_non_wind_pon(self):
        # ponning a regular tile (e.g. 1m) does not trigger pao
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        man_1m = TilesConverter.string_to_136_array(man="111")
        player.tiles = [man_1m[0], man_1m[1], *TilesConverter.string_to_136_array(pin="1234", sou="1234")]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[2])

        assert player.pao_seat is None

    def test_pao_with_kan_dragon_melds(self):
        # player 0 has kan of haku and kan of hatsu, then pons chun
        # kan melds should count toward dragon set count
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        haku = TilesConverter.string_to_136_array(honors="5555")
        hatsu = TilesConverter.string_to_136_array(honors="6666")
        chun = TilesConverter.string_to_136_array(honors="777")
        player.melds = [
            Meld(
                meld_type=Meld.KAN,
                tiles=haku,
                opened=True,
                called_tile=haku[3],
                who=0,
                from_who=2,
            ),
            Meld(
                meld_type=Meld.KAN,
                tiles=hatsu,
                opened=True,
                called_tile=hatsu[3],
                who=0,
                from_who=1,
            ),
        ]
        player.tiles = [chun[0], chun[1], *TilesConverter.string_to_136_array(pin="1234", sou="1")]

        call_pon(round_state, caller_seat=0, discarder_seat=1, tile_id=chun[2])

        assert player.pao_seat == 1

    def test_pao_with_shouminkan_dragon_melds(self):
        # player 0 has shouminkan of haku and pon of hatsu, then pons chun
        round_state = self._create_round_state_with_dead_wall()
        player = round_state.players[0]
        haku = TilesConverter.string_to_136_array(honors="5555")
        hatsu = TilesConverter.string_to_136_array(honors="666")
        chun = TilesConverter.string_to_136_array(honors="777")
        player.melds = [
            Meld(
                meld_type=Meld.SHOUMINKAN,
                tiles=haku,
                opened=True,
                called_tile=haku[2],
                who=0,
                from_who=2,
            ),
            Meld(meld_type=Meld.PON, tiles=hatsu, opened=True, called_tile=hatsu[2], who=0, from_who=1),
        ]
        player.tiles = [chun[0], chun[1], *TilesConverter.string_to_136_array(pin="1234", sou="123")]

        call_pon(round_state, caller_seat=0, discarder_seat=3, tile_id=chun[2])

        assert player.pao_seat == 3
