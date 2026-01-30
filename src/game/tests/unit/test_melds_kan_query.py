"""
Unit tests for kan query functions, riichi kan preservation, and added kan edge cases.
"""

import pytest
from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.melds import (
    _kan_preserves_waits_for_riichi,
    call_added_kan,
    get_possible_added_kans,
    get_possible_closed_kans,
)
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.tests.unit.helpers import _string_to_34_tile, _string_to_34_tiles


class TestGetPossibleClosedKans:
    def _create_player(self, tiles: list[int], *, is_riichi: bool = False) -> MahjongPlayer:
        """Create a player with specified tiles."""
        return MahjongPlayer(seat=0, name="Test", tiles=tiles, is_riichi=is_riichi)

    def _create_round_state(self, player: MahjongPlayer, wall_count: int = 10) -> MahjongRoundState:
        """Create a round state with the given player and wall size."""
        players = [
            player,
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        return MahjongRoundState(players=players, wall=list(range(wall_count)))

    def test_no_possible_kans(self):
        player = self._create_player(TilesConverter.string_to_136_array(man="111", pin="12"))
        round_state = self._create_round_state(player)

        result = get_possible_closed_kans(player, round_state)

        assert result == []

    def test_one_possible_kan(self):
        # player has all 4 copies of 1m
        player = self._create_player(TilesConverter.string_to_136_array(man="1111", pin="12"))
        round_state = self._create_round_state(player)

        result = get_possible_closed_kans(player, round_state)

        assert result == _string_to_34_tiles(man="1")

    def test_multiple_possible_kans(self):
        # player has all 4 copies of 1m and 1p
        player = self._create_player(TilesConverter.string_to_136_array(man="1111", pin="1111"))
        round_state = self._create_round_state(player)

        result = get_possible_closed_kans(player, round_state)

        assert sorted(result) == _string_to_34_tiles(man="1", pin="1")

    def test_no_kans_when_wall_too_small(self):
        player = self._create_player(TilesConverter.string_to_136_array(man="1111"))
        round_state = self._create_round_state(player, wall_count=1)

        result = get_possible_closed_kans(player, round_state)

        assert result == []

    def test_no_kans_when_max_kans_reached(self):
        player = self._create_player(TilesConverter.string_to_136_array(man="1111", pin="12"))
        round_state = self._create_round_state(player)
        round_state.players[1].melds = [
            Meld(
                meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="5555"), opened=True, who=1
            ),
            Meld(
                meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="6666"), opened=True, who=1
            ),
        ]
        round_state.players[2].melds = [
            Meld(
                meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="7777"), opened=True, who=2
            ),
            Meld(
                meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="8888"), opened=True, who=2
            ),
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
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        return MahjongRoundState(players=players, wall=list(range(wall_count)))

    def test_no_possible_added_kans(self):
        player = MahjongPlayer(
            seat=0,
            name="Test",
            tiles=TilesConverter.string_to_136_array(pin="123"),
        )
        round_state = self._create_round_state(player)

        result = get_possible_added_kans(player, round_state)

        assert result == []

    def test_one_possible_added_kan(self):
        # player has pon of 1m and 4th tile in hand
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player_with_pon(
            [man_1m[3], *TilesConverter.string_to_136_array(pin="12")],
            pon_tile_34=_string_to_34_tile(man="1"),
        )
        round_state = self._create_round_state(player)

        result = get_possible_added_kans(player, round_state)

        assert result == _string_to_34_tiles(man="1")

    def test_multiple_possible_added_kans(self):
        # player has two pons and both 4th tiles
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_1p = TilesConverter.string_to_136_array(pin="1111")
        player = self._create_player_with_pon(
            [man_1m[3], pin_1p[3], *TilesConverter.string_to_136_array(pin="3")],
            pon_tile_34=_string_to_34_tile(man="1"),
        )
        # add another pon
        pin_1p_pon = TilesConverter.string_to_136_array(pin="111")
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=pin_1p_pon,
            opened=True,
            called_tile=pin_1p_pon[2],
            who=0,
            from_who=2,
        )
        player.melds.append(pon_meld)
        round_state = self._create_round_state(player)

        result = get_possible_added_kans(player, round_state)

        assert sorted(result) == _string_to_34_tiles(man="1", pin="1")

    def test_no_added_kans_when_in_riichi(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player_with_pon(
            [man_1m[3], *TilesConverter.string_to_136_array(pin="12")],
            pon_tile_34=_string_to_34_tile(man="1"),
        )
        player.is_riichi = True
        round_state = self._create_round_state(player)

        result = get_possible_added_kans(player, round_state)

        assert result == []

    def test_no_added_kans_when_wall_too_small(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player_with_pon(
            [man_1m[3], *TilesConverter.string_to_136_array(pin="12")],
            pon_tile_34=_string_to_34_tile(man="1"),
        )
        round_state = self._create_round_state(player, wall_count=1)

        result = get_possible_added_kans(player, round_state)

        assert result == []

    def test_no_added_kans_when_max_kans_reached(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player_with_pon(
            [man_1m[3], *TilesConverter.string_to_136_array(pin="12")],
            pon_tile_34=_string_to_34_tile(man="1"),
        )
        round_state = self._create_round_state(player)
        round_state.players[1].melds = [
            Meld(
                meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="5555"), opened=True, who=1
            ),
            Meld(
                meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="6666"), opened=True, who=1
            ),
        ]
        round_state.players[2].melds = [
            Meld(
                meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="7777"), opened=True, who=2
            ),
            Meld(
                meld_type=Meld.SHOUMINKAN,
                tiles=TilesConverter.string_to_136_array(pin="8888"),
                opened=True,
                who=2,
            ),
        ]

        result = get_possible_added_kans(player, round_state)

        assert result == []


class TestKanPreservesWaitsForRiichi:
    def test_no_waits_returns_false(self):
        """Player not in tempai cannot declare kan during riichi."""
        # scattered tiles that are definitely not in tempai
        # 1m 3m 5m 7m 9m 2p 4p 6p 8p 1s 3s 5s 7s (all odd man, even pin, odd sou)
        player = MahjongPlayer(
            seat=0,
            name="P0",
            tiles=TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357"),
            is_riichi=True,
        )
        result = _kan_preserves_waits_for_riichi(player, _string_to_34_tile(man="1"))

        assert result is False

    def test_kan_tile_is_wait_returns_false(self):
        """Cannot kan a tile that is one of the waiting tiles."""
        # tempai hand: 123m 456m 789m 111p, waiting for 2p (tile_34=10)
        player = MahjongPlayer(
            seat=0,
            name="P0",
            tiles=(
                TilesConverter.string_to_136_array(man="123456789")
                + TilesConverter.string_to_136_array(pin="111")
                + TilesConverter.string_to_136_array(pin="2")
            ),
            is_riichi=True,
        )
        # waiting for 2p (tile_34=10). Try to kan tile_34=10.
        result = _kan_preserves_waits_for_riichi(player, _string_to_34_tile(pin="2"))

        assert result is False


class TestGetPossibleClosedKansRiichi:
    def test_riichi_player_kan_changes_waits_excluded(self):
        """Riichi player cannot declare kan if it changes waiting tiles."""
        # hand: 1m*4 2m*3 3m*3 4m 4m 5m (13 tiles)
        # this hand structure: kan on 1m would change the hand's waiting tiles
        player = MahjongPlayer(
            seat=0,
            name="P0",
            tiles=(
                TilesConverter.string_to_136_array(man="1111")
                + TilesConverter.string_to_136_array(man="222")
                + TilesConverter.string_to_136_array(man="333")
                + TilesConverter.string_to_136_array(man="44")
                + TilesConverter.string_to_136_array(man="5")
            ),
            is_riichi=True,
        )
        round_state = MahjongRoundState(
            wall=list(range(50)),
            players=[player] + [MahjongPlayer(seat=i, name=f"P{i}") for i in range(1, 4)],
        )
        result = get_possible_closed_kans(player, round_state)

        # with this hand, kan on 1m changes waits, so it should be excluded
        assert isinstance(result, list)
        assert _string_to_34_tile(man="1") not in result

    def test_riichi_player_kan_tile_is_wait_excluded(self):
        """Riichi player cannot declare kan when the tile is one of the waiting tiles."""
        # hand: 333m 45m 456p 789p 22s (13 tiles, tenpai on 3m/6m/2s)
        # player draws 4th 3m → 14 tiles. kan on 3m rejected because 3m is a wait.
        base_hand = TilesConverter.string_to_136_array(man="33345", pin="456789", sou="22")
        fourth_3m_candidates = TilesConverter.string_to_136_array(man="3333")
        fourth_3m = [t for t in fourth_3m_candidates if t not in base_hand]
        hand_14 = [*base_hand, fourth_3m[0]]

        player = MahjongPlayer(
            seat=0,
            name="P0",
            tiles=hand_14,
            is_riichi=True,
        )
        round_state = MahjongRoundState(
            wall=list(range(50)),
            players=[player] + [MahjongPlayer(seat=i, name=f"P{i}") for i in range(1, 4)],
        )
        result = get_possible_closed_kans(player, round_state)

        assert _string_to_34_tile(man="3") not in result

    def test_riichi_player_kan_preserves_waits_included(self):
        """Riichi player can declare kan on an isolated triplet that does not affect waits."""
        # hand: 1112245678999m (13 tiles before draw, tenpai on 6m/9m)
        # structure: 111m(set) + 999m(set) + 456m(chi) + 22m(pair) + 78m(wait)
        # player draws 4th 1m → 14 tiles. kan on 1m preserves waits (6m, 9m).
        base_hand = TilesConverter.string_to_136_array(man="1112245678999")
        fourth_1m_candidates = TilesConverter.string_to_136_array(man="1111")
        fourth_1m = [t for t in fourth_1m_candidates if t not in base_hand]
        hand_14 = [*base_hand, fourth_1m[0]]

        player = MahjongPlayer(
            seat=0,
            name="P0",
            tiles=hand_14,
            is_riichi=True,
        )
        round_state = MahjongRoundState(
            wall=list(range(50)),
            players=[player] + [MahjongPlayer(seat=i, name=f"P{i}") for i in range(1, 4)],
        )
        result = get_possible_closed_kans(player, round_state)

        assert _string_to_34_tile(man="1") in result


class TestCallAddedKanNullPonTiles:
    def test_added_kan_raises_when_pon_tiles_is_none(self):
        """Pon meld with tiles set to None after discovery raises ValueError."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        man_2m = TilesConverter.string_to_136_array(man="222")
        man_3m = TilesConverter.string_to_136_array(man="333")
        man_4m = TilesConverter.string_to_136_array(man="444")
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        players = [
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=([man_1m[3], *TilesConverter.string_to_136_array(pin="1234", sou="1234", honors="1")]),
            ),
            MahjongPlayer(
                seat=1,
                name="Bot1",
                tiles=man_2m + TilesConverter.string_to_136_array(pin="5"),
            ),
            MahjongPlayer(
                seat=2,
                name="Bot2",
                tiles=man_3m + TilesConverter.string_to_136_array(pin="6"),
            ),
            MahjongPlayer(
                seat=3,
                name="Bot3",
                tiles=man_4m + TilesConverter.string_to_136_array(pin="7"),
            ),
        ]
        pon_meld = Meld(
            meld_type=Meld.PON,
            tiles=pon_tiles,
            opened=True,
            called_tile=pon_tiles[2],
            who=0,
            from_who=1,
        )
        players[0].melds.append(pon_meld)

        west = TilesConverter.string_to_136_array(honors="3333")
        north = TilesConverter.string_to_136_array(honors="4444")
        haku = TilesConverter.string_to_136_array(honors="5555")
        hatsu = TilesConverter.string_to_136_array(honors="66")
        round_state = MahjongRoundState(
            players=players,
            current_player_seat=0,
            wall=list(range(120, 136)),
            dead_wall=west + north + haku + hatsu,
            dora_indicators=[west[2]],
            players_with_open_hands=[0],
        )

        # use a custom list that nullifies pon_meld.tiles when remove() is called
        class NullifyingList(list):
            def remove(self, value: int) -> None:
                super().remove(value)
                pon_meld.tiles = None

        players[0].tiles = NullifyingList(players[0].tiles)

        with pytest.raises(ValueError, match="pon meld tiles cannot be None"):
            call_added_kan(round_state, seat=0, tile_id=man_1m[3])
