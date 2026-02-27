"""Unit tests for meld edge cases: kuikae suji, 4-kan limit, riichi kan waits, and pao liability."""

import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import MeldCallType
from game.logic.exceptions import InvalidMeldError
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import (
    _check_pao,
    _kan_preserves_waits_for_riichi,
    _validate_chi_sequence,
    call_chi,
    call_open_kan,
    call_pon,
    can_call_open_kan,
    get_kuikae_tiles,
    get_possible_added_kans,
    get_possible_closed_kans,
)
from game.logic.settings import GameSettings
from game.logic.tiles import tile_to_34
from game.tests.conftest import create_player, create_round_state


class TestKuikaeEdgeCases:
    """Test kuikae edge cases for chi calls."""

    def test_kuikae_called_tile_highest(self):
        """Test chi suji kuikae when called tile is highest in sequence.

        When calling chi with tile as highest (e.g., 3m in 123m), the suji extends
        below the lowest tile. Verify forbidden tiles include both called tile and suji.
        """
        # Create sequence 123m where called_tile is 3m (tile_34=2 in man suit)
        man_tiles = TilesConverter.string_to_136_array(man="123")
        called_tile_34 = tile_to_34(man_tiles[2])  # 3m is tile_34 = 2
        sequence_tiles_34 = [tile_to_34(man_tiles[0]), tile_to_34(man_tiles[1])]  # 1m, 2m

        forbidden = get_kuikae_tiles(MeldCallType.CHI, called_tile_34, sequence_tiles_34)

        # Should forbid 3m (called tile) and the suji below 1m (which is 0m, but doesn't exist)
        # Actually: sequence is [0, 1, 2], called is 2 (highest)
        # suji = all_tiles[0] - 1 = 0 - 1 = -1, but -1 < 0, so it's filtered out
        # So only the called tile should be forbidden
        assert called_tile_34 in forbidden
        # The suji would be -1, which is invalid, so it won't be in the list
        # But let's test with a valid case: 234m where 4m is called
        man_tiles_234 = TilesConverter.string_to_136_array(man="234")
        called_tile_34_4m = tile_to_34(man_tiles_234[2])  # 4m
        sequence_tiles_34_23 = [tile_to_34(man_tiles_234[0]), tile_to_34(man_tiles_234[1])]  # 2m, 3m

        forbidden_234 = get_kuikae_tiles(MeldCallType.CHI, called_tile_34_4m, sequence_tiles_34_23)

        # Sequence is [1, 2, 3] (234m in tile_34), called is 3 (4m)
        # suji = all_tiles[0] - 1 = 1 - 1 = 0 (1m)
        assert called_tile_34_4m in forbidden_234  # 4m
        assert 0 in forbidden_234  # 1m (suji tile)


class TestKanLimits:
    """Test 4-kan limit restrictions."""

    def test_open_kan_blocked_by_insufficient_wall(self):
        """Open kan requires min_wall_for_kan tiles in the wall even when player has 3 matching."""
        pin_5p = TilesConverter.string_to_136_array(pin="555")
        player = create_player(seat=1, tiles=pin_5p)
        round_state = create_round_state(
            players=[create_player(seat=0), player, create_player(seat=2), create_player(seat=3)],
            wall=(1,),  # only 1 tile; min_wall_for_kan defaults to 2
        )
        discarded_tile = TilesConverter.string_to_136_array(pin="5")[0]
        assert can_call_open_kan(player, discarded_tile, round_state, GameSettings()) is False

    def test_four_kan_limit_blocks_open_kan(self):
        """Test that 4 existing kans blocks new open kan."""
        # Create players with 4 total kans
        man_1234 = TilesConverter.string_to_136_array(man="1111222233334444")

        # Player 0 has 2 kans
        player0_melds = (
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[0:4]),
                opened=True,
                who=0,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[4:8]),
                opened=False,
                who=0,
            ),
        )

        # Player 1 has 2 kans
        player1_melds = (
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[8:12]),
                opened=True,
                who=1,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.SHOUMINKAN,
                tiles=tuple(man_1234[12:16]),
                opened=True,
                who=1,
            ),
        )

        # Player 2 has 3 matching tiles for a potential 5th kan
        pin_5p = TilesConverter.string_to_136_array(pin="555")
        player2 = create_player(seat=2, tiles=pin_5p)

        players = [
            create_player(seat=0, melds=player0_melds),
            create_player(seat=1, melds=player1_melds),
            player2,
            create_player(seat=3),
        ]

        wall = tuple(TilesConverter.string_to_136_array(sou="123456"))
        round_state = create_round_state(players=players, wall=wall)

        discarded_tile = TilesConverter.string_to_136_array(pin="5")[0]

        settings = GameSettings()
        result = can_call_open_kan(player2, discarded_tile, round_state, settings)

        assert result is False

    def test_four_kan_limit_blocks_closed_kan(self):
        """Test that 4 existing kans blocks closed kan."""
        # Create players with 4 total kans
        man_1234 = TilesConverter.string_to_136_array(man="1111222233334444")

        player0_melds = (
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[0:4]),
                opened=True,
                who=0,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[4:8]),
                opened=False,
                who=0,
            ),
        )

        player1_melds = (
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[8:12]),
                opened=True,
                who=1,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[12:16]),
                opened=True,
                who=1,
            ),
        )

        # Player 2 has 4 matching tiles
        pin_5p = TilesConverter.string_to_136_array(pin="5555")
        player2 = create_player(seat=2, tiles=pin_5p)

        players = [
            create_player(seat=0, melds=player0_melds),
            create_player(seat=1, melds=player1_melds),
            player2,
            create_player(seat=3),
        ]

        wall = tuple(TilesConverter.string_to_136_array(sou="123456"))
        round_state = create_round_state(players=players, wall=wall)

        settings = GameSettings()
        result = get_possible_closed_kans(player2, round_state, settings)

        assert result == []

    def test_four_kan_limit_blocks_added_kan(self):
        """Test that 4 existing kans blocks added kan."""
        # Create players with 4 total kans
        man_1234 = TilesConverter.string_to_136_array(man="1111222233334444")

        player0_melds = (
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[0:4]),
                opened=True,
                who=0,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[4:8]),
                opened=False,
                who=0,
            ),
        )

        player1_melds = (
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[8:12]),
                opened=True,
                who=1,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(man_1234[12:16]),
                opened=True,
                who=1,
            ),
        )

        # Player 2 has a pon and the 4th tile
        pin_5p = TilesConverter.string_to_136_array(pin="5555")
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pin_5p[0:3]),
            opened=True,
            who=2,
        )
        player2 = create_player(seat=2, tiles=[pin_5p[3]], melds=[pon_meld])

        players = [
            create_player(seat=0, melds=player0_melds),
            create_player(seat=1, melds=player1_melds),
            player2,
            create_player(seat=3),
        ]

        wall = tuple(TilesConverter.string_to_136_array(sou="123456"))
        round_state = create_round_state(players=players, wall=wall)

        settings = GameSettings()
        result = get_possible_added_kans(player2, round_state, settings)

        assert result == []


class TestRiichiKanWaitPreservation:
    """Test kan wait preservation checks for riichi players."""

    def test_kan_preserves_waits_allows(self):
        """Test closed kan during riichi that preserves waits (allowed).

        Hand: 1111m 234p 567p 89s 55s (14 tiles, riichi player just drew).
        Remove one 1m -> 111m 234p 567p 89s 55s = 13 tiles tenpai on 7s.
        Kan on 1m: remove all four 1m -> 234p 567p 89s 55s + kan meld.
        Still tenpai on 7s -> waits preserved.
        """
        tiles = TilesConverter.string_to_136_array(man="1111", pin="234567", sou="8955")

        player = create_player(seat=0, tiles=tiles, is_riichi=True)

        # Check if kan on 1m preserves waits
        tile_34_1m = tile_to_34(tiles[0])  # 1m

        result = _kan_preserves_waits_for_riichi(player, tile_34_1m)

        assert result is True

    def test_kan_preserves_waits_rejects(self):
        """Test closed kan during riichi that changes waits (rejected).

        Hand where kan would change the waiting tiles.
        """
        # Create a hand where kan changes waits
        # Hand: 1112345678999m (tenpai on 1m, 4m, 7m)
        # If we kan 1111m or 9999m, waits change
        tiles = TilesConverter.string_to_136_array(man="1112345678999")

        player = create_player(seat=0, tiles=tiles, is_riichi=True)

        # Check if kan on 1m changes waits
        tile_34_1m = tile_to_34(tiles[0])  # 1m

        result = _kan_preserves_waits_for_riichi(player, tile_34_1m)

        # This should be rejected because kan changes the hand structure
        assert result is False

    def test_kan_rejected_when_tile_is_also_a_wait(self):
        """Test closed kan during riichi rejected when kan tile is also a wait.

        Hand: 11234m 567s 789999p (14 tiles, riichi player just drew 4th 9p).
        Remove one 9p -> 11234m 567s 78999p = 13 tiles.
        Tenpai readings:
        - 234m + 567s + 999p + 11m + 78p -> wait on 6p or 9p
        - 234m + 567s + 789p + 99p + 11m -> shanpon wait on 1m or 9p
        Since 9p is among the waits, kan on 9p must be rejected.
        """
        tiles = TilesConverter.string_to_136_array(man="11234", sou="567", pin="789999")

        player = create_player(seat=0, tiles=tiles, is_riichi=True)

        # 9p in 34-format = 17
        nine_pin_tiles = TilesConverter.string_to_136_array(pin="9")
        tile_34_9p = tile_to_34(nine_pin_tiles[0])

        result = _kan_preserves_waits_for_riichi(player, tile_34_9p)

        assert result is False

    def test_possible_closed_kans_includes_wait_preserving_kan(self):
        """get_possible_closed_kans includes riichi kan when drawn tile is the kan tile.

        Hand: 111m 234567p 8955s + drawn 1m (last tile).
        The drawn tile (4th 1m) completes the quad and preserves waits.
        """
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin = TilesConverter.string_to_136_array(pin="234567")
        sou = TilesConverter.string_to_136_array(sou="8955")
        # place 4th 1m last as drawn tile
        tiles = list(man_1m[:3]) + list(pin) + list(sou) + [man_1m[3]]
        player = create_player(seat=0, tiles=tiles, is_riichi=True)

        players = [player] + [create_player(seat=i) for i in range(1, 4)]
        wall = tuple(TilesConverter.string_to_136_array(sou="123456"))
        dead_wall = tuple(TilesConverter.string_to_136_array(pin="11112222333344"))
        round_state = create_round_state(players=players, wall=wall, dead_wall=dead_wall)

        result = get_possible_closed_kans(player, round_state, GameSettings())
        tile_34_1m = tile_to_34(man_1m[0])
        assert tile_34_1m in result

    def test_riichi_kan_blocked_when_drawn_tile_is_not_kan_tile(self):
        """Closed kan during riichi requires the drawn tile to be the kan tile.

        Hand: 1111m 234567p 89s + drawn 5s (last tile).
        Player has 4x 1m but drew 5s, so kan on 1m is blocked because
        the drawn tile is not the kan tile.
        """
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin = TilesConverter.string_to_136_array(pin="234567")
        sou = TilesConverter.string_to_136_array(sou="8955")
        # drawn tile (last) is 5s, NOT 1m
        tiles = list(man_1m) + list(pin) + list(sou)
        player = create_player(seat=0, tiles=tiles, is_riichi=True)

        players = [player] + [create_player(seat=i) for i in range(1, 4)]
        wall = tuple(TilesConverter.string_to_136_array(sou="123456"))
        dead_wall = tuple(TilesConverter.string_to_136_array(pin="11112222333344"))
        round_state = create_round_state(players=players, wall=wall, dead_wall=dead_wall)

        result = get_possible_closed_kans(player, round_state, GameSettings())
        assert result == []


class TestPaoLiability:
    """Test pao liability for daisangen and daisuushii."""

    def test_pao_liability_three_dragons(self):
        """Test pon on 3rd dragon triggers pao (daisangen).

        Create player with 2 existing dragon pon/kan melds.
        Call _check_pao with 3rd dragon. Verify returns discarder_seat.
        """
        # Create player with 2 dragon melds (haku and hatsu)
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        hatsu_tiles = TilesConverter.string_to_136_array(honors="666")

        melds = (
            FrozenMeld(
                meld_type=FrozenMeld.PON,
                tiles=tuple(haku_tiles),
                opened=True,
                who=0,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.PON,
                tiles=tuple(hatsu_tiles),
                opened=True,
                who=0,
            ),
        )

        player = create_player(seat=0, melds=melds)

        # Call _check_pao with chun (3rd dragon)
        chun_tile = TilesConverter.string_to_136_array(honors="7")[0]
        chun_34 = tile_to_34(chun_tile)
        discarder_seat = 2

        result = _check_pao(player, discarder_seat, chun_34, GameSettings())

        assert result == discarder_seat

    def test_pao_liability_four_winds(self):
        """Test pon on 4th wind triggers pao (daisuushii).

        Create player with 3 existing wind pon/kan melds.
        Call _check_pao with 4th wind. Verify returns discarder_seat.
        """
        # Create player with 3 wind melds (east, south, west)
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        south_tiles = TilesConverter.string_to_136_array(honors="222")
        west_tiles = TilesConverter.string_to_136_array(honors="333")

        melds = (
            FrozenMeld(
                meld_type=FrozenMeld.PON,
                tiles=tuple(east_tiles),
                opened=True,
                who=0,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.PON,
                tiles=tuple(south_tiles),
                opened=True,
                who=0,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=(*tuple(west_tiles), TilesConverter.string_to_136_array(honors="3")[0]),
                opened=True,
                who=0,
            ),
        )

        player = create_player(seat=0, melds=melds)

        # Call _check_pao with north (4th wind)
        north_tile = TilesConverter.string_to_136_array(honors="4")[0]
        north_34 = tile_to_34(north_tile)
        discarder_seat = 3

        result = _check_pao(player, discarder_seat, north_34, GameSettings())

        assert result == discarder_seat

    def test_no_pao_liability_normal_tile(self):
        """Test normal tile returns None (no pao).

        Call _check_pao with a normal numbered tile. Verify returns None.
        """
        player = create_player(seat=0)

        # Call _check_pao with 1m (normal tile)
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        tile_34 = tile_to_34(man_1m)
        discarder_seat = 1

        result = _check_pao(player, discarder_seat, tile_34, GameSettings())

        assert result is None

    def test_no_pao_on_first_dragon_meld(self):
        """Test pon on 1st dragon returns None (need 3 for daisangen pao).

        Player has 0 dragon melds, calling pon on haku. count=0, count+1=1 < 3.
        Hits the break+return None path.
        """
        player = create_player(seat=0)

        haku_tile = TilesConverter.string_to_136_array(honors="5")[0]
        haku_34 = tile_to_34(haku_tile)
        discarder_seat = 2

        result = _check_pao(player, discarder_seat, haku_34, GameSettings())

        assert result is None

    def test_pao_liability_open_kan(self):
        """Test open kan on 3rd dragon triggers pao.

        Call call_open_kan with 3rd dragon tile on player with 2 dragon melds.
        Verify returned state has pao_seat set.
        """
        # Create player with 2 dragon melds and 3 chun tiles
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        hatsu_tiles = TilesConverter.string_to_136_array(honors="666")
        chun_tiles = TilesConverter.string_to_136_array(honors="777")

        melds = (
            FrozenMeld(
                meld_type=FrozenMeld.PON,
                tiles=tuple(haku_tiles),
                opened=True,
                who=0,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=(*tuple(hatsu_tiles), TilesConverter.string_to_136_array(honors="6")[0]),
                opened=True,
                who=0,
            ),
        )

        # Player has 3 chun tiles in hand
        player = create_player(seat=0, tiles=chun_tiles[:3], melds=melds)

        players = [player] + [create_player(seat=i) for i in range(1, 4)]
        wall = tuple(TilesConverter.string_to_136_array(man="123456"))
        dead_wall = tuple(TilesConverter.string_to_136_array(pin="11112222333344"))
        round_state = create_round_state(players=players, wall=wall, dead_wall=dead_wall)

        # Call open kan on 4th chun
        discarder_seat = 2
        chun_4th = TilesConverter.string_to_136_array(honors="7")[0]

        settings = GameSettings()
        new_state, _meld = call_open_kan(
            round_state,
            caller_seat=0,
            discarder_seat=discarder_seat,
            tile_id=chun_4th,
            settings=settings,
        )

        assert new_state.players[0].pao_seat == discarder_seat

    def test_pao_liability_pon(self):
        """Test pon on 3rd dragon sets pao_seat.

        Call call_pon with 3rd dragon tile on player with 2 existing dragon melds.
        Verify pao_seat is set in result.
        """
        # Create player with 2 dragon melds and 2 chun tiles
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        hatsu_tiles = TilesConverter.string_to_136_array(honors="666")
        chun_tiles = TilesConverter.string_to_136_array(honors="77")

        melds = (
            FrozenMeld(
                meld_type=FrozenMeld.PON,
                tiles=tuple(haku_tiles),
                opened=True,
                who=0,
            ),
            FrozenMeld(
                meld_type=FrozenMeld.PON,
                tiles=tuple(hatsu_tiles),
                opened=True,
                who=0,
            ),
        )

        # Player has 2 chun tiles in hand
        other_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player = create_player(seat=0, tiles=tuple(chun_tiles) + tuple(other_tiles), melds=melds)

        players = [player] + [create_player(seat=i) for i in range(1, 4)]
        wall = tuple(TilesConverter.string_to_136_array(man="123456"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333344"))
        round_state = create_round_state(players=players, wall=wall, dead_wall=dead_wall)

        # Call pon on 3rd chun
        discarder_seat = 3
        chun_3rd = TilesConverter.string_to_136_array(honors="7")[0]

        settings = GameSettings()
        new_state, _meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=discarder_seat,
            tile_id=chun_3rd,
            settings=settings,
        )

        assert new_state.players[0].pao_seat == discarder_seat


class TestChiKuikaeWithoutSuji:
    """Test chi kuikae restriction without suji extension."""

    def test_chi_kuikae_no_suji(self):
        """Test call_chi with has_kuikae=True, has_kuikae_suji=False.

        When kuikae is enabled but suji is not, only the called tile type
        should be forbidden (not the suji extension).
        """
        man_tiles = TilesConverter.string_to_136_array(man="123")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player1_tiles = (man_tiles[1], man_tiles[2], *pin_tiles)

        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]

        settings = GameSettings(has_kuikae=True, has_kuikae_suji=False)
        round_state = create_round_state(
            players=players,
            current_player_seat=0,
        )

        new_state, _meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        called_34 = tile_to_34(man_tiles[0])
        # Only the called tile type should be forbidden (no suji)
        assert new_state.players[1].kuikae_tiles == (called_34,)


class TestValidateChiSequence:
    """Tests for _validate_chi_sequence defense-in-depth validation."""

    def test_rejects_honor_tiles(self):
        honors = TilesConverter.string_to_136_array(honors="123")
        with pytest.raises(InvalidMeldError, match="honor tiles"):
            _validate_chi_sequence(honors[0], (honors[1], honors[2]))

    def test_rejects_mixed_suits(self):
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        pin_2 = TilesConverter.string_to_136_array(pin="2")[0]
        sou_3 = TilesConverter.string_to_136_array(sou="3")[0]
        with pytest.raises(InvalidMeldError, match="same suit"):
            _validate_chi_sequence(man_1, (pin_2, sou_3))

    def test_rejects_non_consecutive(self):
        man_tiles = TilesConverter.string_to_136_array(man="124")
        with pytest.raises(InvalidMeldError, match="consecutive sequence"):
            _validate_chi_sequence(man_tiles[0], (man_tiles[1], man_tiles[2]))

    def test_accepts_valid_chi(self):
        man_tiles = TilesConverter.string_to_136_array(man="123")
        # Should not raise
        _validate_chi_sequence(man_tiles[0], (man_tiles[1], man_tiles[2]))


class TestCheckPaoDisabled:
    """Tests for _check_pao when pao settings are disabled."""

    def test_pao_disabled_for_dragons_returns_none(self):
        """When daisangen pao is disabled, calling a 3rd dragon returns None."""
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        hatsu_tiles = TilesConverter.string_to_136_array(honors="666")

        melds = (
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(haku_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(hatsu_tiles), opened=True, who=0),
        )
        player = create_player(seat=0, melds=melds)

        chun_tile = TilesConverter.string_to_136_array(honors="7")[0]
        chun_34 = tile_to_34(chun_tile)

        settings = GameSettings(has_daisangen_pao=False)
        result = _check_pao(player, 2, chun_34, settings)
        assert result is None

    def test_pao_disabled_for_winds_returns_none(self):
        """When daisuushii pao is disabled, calling a 4th wind returns None."""
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        south_tiles = TilesConverter.string_to_136_array(honors="222")
        west_tiles = TilesConverter.string_to_136_array(honors="333")

        melds = (
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(east_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(south_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(west_tiles), opened=True, who=0),
        )
        player = create_player(seat=0, melds=melds)

        north_tile = TilesConverter.string_to_136_array(honors="4")[0]
        north_34 = tile_to_34(north_tile)

        settings = GameSettings(has_daisuushii_pao=False)
        result = _check_pao(player, 3, north_34, settings)
        assert result is None
