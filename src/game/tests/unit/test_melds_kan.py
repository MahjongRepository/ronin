"""
Unit tests for kan meld operations (open kan, closed kan, added kan, four kans check).
"""

import pytest
from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.abortive import check_four_kans
from game.logic.melds import (
    call_added_kan,
    call_closed_kan,
    call_open_kan,
    can_call_open_kan,
)
from game.logic.state import MahjongPlayer, MahjongRoundState


class TestCanCallOpenKan:
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

    def test_can_call_open_kan_with_three_matching_tiles(self):
        # player has 1m 1m 1m in hand
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player(
            [man_1m[0], man_1m[1], man_1m[2], *TilesConverter.string_to_136_array(pin="1")]
        )
        round_state = self._create_round_state(player)

        result = can_call_open_kan(player, discarded_tile=man_1m[3], round_state=round_state)

        assert result is True

    def test_cannot_call_open_kan_with_two_matching_tiles(self):
        # player has only 2 matching tiles
        man_1m = TilesConverter.string_to_136_array(man="111")
        player = self._create_player(
            [man_1m[0], man_1m[1], *TilesConverter.string_to_136_array(pin="1", sou="1")]
        )
        round_state = self._create_round_state(player)

        result = can_call_open_kan(player, discarded_tile=man_1m[2], round_state=round_state)

        assert result is False

    def test_cannot_call_open_kan_when_in_riichi(self):
        # player is in riichi
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player(
            [man_1m[0], man_1m[1], man_1m[2], *TilesConverter.string_to_136_array(pin="1")],
            is_riichi=True,
        )
        round_state = self._create_round_state(player)

        result = can_call_open_kan(player, discarded_tile=man_1m[3], round_state=round_state)

        assert result is False

    def test_cannot_call_open_kan_when_wall_too_small(self):
        # wall has less than 2 tiles
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player(
            [man_1m[0], man_1m[1], man_1m[2], *TilesConverter.string_to_136_array(pin="1")]
        )
        round_state = self._create_round_state(player, wall_count=1)

        result = can_call_open_kan(player, discarded_tile=man_1m[3], round_state=round_state)

        assert result is False

    def test_cannot_call_open_kan_wall_empty(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player(
            [man_1m[0], man_1m[1], man_1m[2], *TilesConverter.string_to_136_array(pin="1")]
        )
        round_state = self._create_round_state(player, wall_count=0)

        result = can_call_open_kan(player, discarded_tile=man_1m[3], round_state=round_state)

        assert result is False

    def test_cannot_call_open_kan_when_max_kans_reached(self):
        # 4 kans already declared across players
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player = self._create_player(
            [man_1m[0], man_1m[1], man_1m[2], *TilesConverter.string_to_136_array(pin="1")]
        )
        round_state = self._create_round_state(player)
        # add 4 kan melds to other players
        kan_meld = Meld(
            meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="2222"), opened=True, who=1
        )
        round_state.players[1].melds = [
            kan_meld,
            Meld(
                meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="3333"), opened=True, who=1
            ),
        ]
        round_state.players[2].melds = [
            Meld(meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="4444"), opened=True, who=2)
        ]
        round_state.players[3].melds = [
            Meld(meld_type=Meld.KAN, tiles=TilesConverter.string_to_136_array(pin="5555"), opened=True, who=3)
        ]

        result = can_call_open_kan(player, discarded_tile=man_1m[3], round_state=round_state)

        assert result is False


class TestCallOpenKan:
    def _create_round_state_with_dead_wall(self) -> MahjongRoundState:
        """Create a round state with proper dead wall setup."""
        man_1m = TilesConverter.string_to_136_array(man="111")
        man_2m = TilesConverter.string_to_136_array(man="222")
        man_3m = TilesConverter.string_to_136_array(man="333")
        man_4m = TilesConverter.string_to_136_array(man="444")
        players = [
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=man_1m + TilesConverter.string_to_136_array(pin="1234", sou="1234", honors="12"),
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
        west = TilesConverter.string_to_136_array(honors="3333")
        north = TilesConverter.string_to_136_array(honors="4444")
        haku = TilesConverter.string_to_136_array(honors="5555")
        hatsu = TilesConverter.string_to_136_array(honors="66")
        return MahjongRoundState(
            players=players,
            current_player_seat=1,
            wall=list(range(120, 136)),  # 16 tiles in wall
            dead_wall=west + north + haku + hatsu,
            dora_indicators=[west[2]],  # first dora at index 2
        )

    def test_call_open_kan_removes_tiles_from_hand(self):
        round_state = self._create_round_state_with_dead_wall()
        # player 0 calls kan on 1m discarded by player 1
        # player 0 has 3 copies of 1m
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[3])

        player = round_state.players[0]
        # should have removed 3 tiles and added one from dead wall
        assert man_1m[0] not in player.tiles
        assert man_1m[1] not in player.tiles
        assert man_1m[2] not in player.tiles

    def test_call_open_kan_creates_meld(self):
        round_state = self._create_round_state_with_dead_wall()
        man_1m = TilesConverter.string_to_136_array(man="1111")

        meld = call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[3])

        assert meld.type == Meld.KAN
        assert meld.opened is True
        assert meld.called_tile == man_1m[3]
        assert meld.who == 0
        assert meld.from_who == 1
        assert meld.tiles is not None
        assert len(meld.tiles) == 4
        assert sorted(meld.tiles) == sorted(man_1m)

    def test_call_open_kan_adds_to_open_hands(self):
        round_state = self._create_round_state_with_dead_wall()
        assert round_state.players_with_open_hands == []
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[3])

        assert 0 in round_state.players_with_open_hands

    def test_call_open_kan_clears_ippatsu(self):
        round_state = self._create_round_state_with_dead_wall()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[3])

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_open_kan_defers_dora_indicator(self):
        round_state = self._create_round_state_with_dead_wall()
        initial_dora_count = len(round_state.dora_indicators)
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[3])

        # open kan defers dora reveal until after discard
        assert len(round_state.dora_indicators) == initial_dora_count
        assert round_state.pending_dora_count == 1

    def test_call_open_kan_maintains_dead_wall_size(self):
        round_state = self._create_round_state_with_dead_wall()
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[3])

        # dead wall stays at 14 (one drawn, one replenished from live wall)
        assert len(round_state.dead_wall) == 14

    def test_call_open_kan_sets_rinshan_flag(self):
        round_state = self._create_round_state_with_dead_wall()
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[3])

        assert round_state.players[0].is_rinshan is True

    def test_call_open_kan_sets_current_player(self):
        round_state = self._create_round_state_with_dead_wall()
        assert round_state.current_player_seat == 1
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[3])

        assert round_state.current_player_seat == 0

    def test_call_open_kan_raises_when_not_enough_tiles(self):
        round_state = self._create_round_state_with_dead_wall()
        man_1m = TilesConverter.string_to_136_array(man="1111")
        round_state.players[0].tiles = [
            man_1m[0],
            man_1m[1],
            *TilesConverter.string_to_136_array(pin="1", sou="1"),
        ]

        with pytest.raises(ValueError, match="cannot call open kan"):
            call_open_kan(round_state, caller_seat=0, discarder_seat=1, tile_id=man_1m[3])


class TestCallClosedKan:
    def _create_round_state_with_dead_wall(self) -> MahjongRoundState:
        """Create a round state with proper dead wall setup."""
        man_2m = TilesConverter.string_to_136_array(man="222")
        man_3m = TilesConverter.string_to_136_array(man="333")
        man_4m = TilesConverter.string_to_136_array(man="444")
        players = [
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=(
                    TilesConverter.string_to_136_array(man="1111")
                    + TilesConverter.string_to_136_array(pin="1234", sou="1234", honors="1")
                ),
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
        west = TilesConverter.string_to_136_array(honors="3333")
        north = TilesConverter.string_to_136_array(honors="4444")
        haku = TilesConverter.string_to_136_array(honors="5555")
        hatsu = TilesConverter.string_to_136_array(honors="66")
        return MahjongRoundState(
            players=players,
            current_player_seat=0,
            wall=list(range(120, 136)),
            dead_wall=west + north + haku + hatsu,
            dora_indicators=[west[2]],
        )

    def test_call_closed_kan_removes_tiles_from_hand(self):
        round_state = self._create_round_state_with_dead_wall()
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_closed_kan(round_state, seat=0, tile_id=man_1m[0])

        player = round_state.players[0]
        # all 4 copies of 1m should be removed
        for tile in man_1m:
            assert tile not in player.tiles

    def test_call_closed_kan_creates_closed_meld(self):
        round_state = self._create_round_state_with_dead_wall()
        man_1m = TilesConverter.string_to_136_array(man="1")[0]

        meld = call_closed_kan(round_state, seat=0, tile_id=man_1m)

        assert meld.type == Meld.KAN
        assert meld.opened is False  # closed kan
        assert meld.who == 0
        assert meld.tiles is not None
        assert len(meld.tiles) == 4

    def test_call_closed_kan_does_not_add_to_open_hands(self):
        round_state = self._create_round_state_with_dead_wall()
        assert round_state.players_with_open_hands == []
        man_1m = TilesConverter.string_to_136_array(man="1")[0]

        call_closed_kan(round_state, seat=0, tile_id=man_1m)

        # closed kan keeps hand closed
        assert 0 not in round_state.players_with_open_hands

    def test_call_closed_kan_clears_ippatsu(self):
        round_state = self._create_round_state_with_dead_wall()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True
        man_1m = TilesConverter.string_to_136_array(man="1")[0]

        call_closed_kan(round_state, seat=0, tile_id=man_1m)

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_closed_kan_adds_dora_indicator_immediately(self):
        round_state = self._create_round_state_with_dead_wall()
        initial_dora_count = len(round_state.dora_indicators)
        man_1m = TilesConverter.string_to_136_array(man="1")[0]

        call_closed_kan(round_state, seat=0, tile_id=man_1m)

        # closed kan reveals dora immediately (not deferred)
        assert len(round_state.dora_indicators) == initial_dora_count + 1
        assert round_state.pending_dora_count == 0

    def test_call_closed_kan_maintains_dead_wall_size(self):
        round_state = self._create_round_state_with_dead_wall()
        man_1m = TilesConverter.string_to_136_array(man="1")[0]

        call_closed_kan(round_state, seat=0, tile_id=man_1m)

        # dead wall stays at 14 (one drawn, one replenished from live wall)
        assert len(round_state.dead_wall) == 14

    def test_call_closed_kan_sets_rinshan_flag(self):
        round_state = self._create_round_state_with_dead_wall()
        man_1m = TilesConverter.string_to_136_array(man="1")[0]

        call_closed_kan(round_state, seat=0, tile_id=man_1m)

        assert round_state.players[0].is_rinshan is True

    def test_call_closed_kan_raises_when_not_enough_tiles(self):
        round_state = self._create_round_state_with_dead_wall()
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="111", pin="1")

        with pytest.raises(ValueError, match="cannot call closed kan"):
            call_closed_kan(round_state, seat=0, tile_id=man_1m)


class TestCallAddedKan:
    def _create_round_state_with_pon(self) -> MahjongRoundState:
        """Create a round state where player 0 has a pon and 4th tile."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        man_2m = TilesConverter.string_to_136_array(man="222")
        man_3m = TilesConverter.string_to_136_array(man="333")
        man_4m = TilesConverter.string_to_136_array(man="444")
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
        # add pon meld to player 0
        pon_tiles = TilesConverter.string_to_136_array(man="111")
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
        return MahjongRoundState(
            players=players,
            current_player_seat=0,
            wall=list(range(120, 136)),
            dead_wall=west + north + haku + hatsu,
            dora_indicators=[west[2]],
            players_with_open_hands=[0],
        )

    def test_call_added_kan_removes_tile_from_hand(self):
        round_state = self._create_round_state_with_pon()
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_added_kan(round_state, seat=0, tile_id=man_1m[3])

        player = round_state.players[0]
        assert man_1m[3] not in player.tiles

    def test_call_added_kan_upgrades_pon_to_shouminkan(self):
        round_state = self._create_round_state_with_pon()
        man_1m = TilesConverter.string_to_136_array(man="1111")

        meld = call_added_kan(round_state, seat=0, tile_id=man_1m[3])

        assert meld.type == Meld.SHOUMINKAN
        assert meld.opened is True
        assert meld.tiles is not None
        assert len(meld.tiles) == 4
        assert sorted(meld.tiles) == sorted(man_1m)

    def test_call_added_kan_replaces_pon_meld(self):
        round_state = self._create_round_state_with_pon()
        player = round_state.players[0]
        assert len(player.melds) == 1
        assert player.melds[0].type == Meld.PON
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_added_kan(round_state, seat=0, tile_id=man_1m[3])

        assert len(player.melds) == 1
        assert player.melds[0].type == Meld.SHOUMINKAN

    def test_call_added_kan_clears_ippatsu(self):
        round_state = self._create_round_state_with_pon()
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_added_kan(round_state, seat=0, tile_id=man_1m[3])

        for player in round_state.players:
            assert player.is_ippatsu is False

    def test_call_added_kan_defers_dora_indicator(self):
        round_state = self._create_round_state_with_pon()
        initial_dora_count = len(round_state.dora_indicators)
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_added_kan(round_state, seat=0, tile_id=man_1m[3])

        # added kan defers dora reveal until after discard
        assert len(round_state.dora_indicators) == initial_dora_count
        assert round_state.pending_dora_count == 1

    def test_call_added_kan_maintains_dead_wall_size(self):
        round_state = self._create_round_state_with_pon()
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_added_kan(round_state, seat=0, tile_id=man_1m[3])

        # dead wall stays at 14 (one drawn, one replenished from live wall)
        assert len(round_state.dead_wall) == 14

    def test_call_added_kan_sets_rinshan_flag(self):
        round_state = self._create_round_state_with_pon()
        man_1m = TilesConverter.string_to_136_array(man="1111")

        call_added_kan(round_state, seat=0, tile_id=man_1m[3])

        assert round_state.players[0].is_rinshan is True

    def test_call_added_kan_raises_when_no_pon(self):
        round_state = self._create_round_state_with_pon()
        round_state.players[0].melds = []  # remove the pon
        man_1m = TilesConverter.string_to_136_array(man="1111")

        with pytest.raises(ValueError, match="cannot call added kan"):
            call_added_kan(round_state, seat=0, tile_id=man_1m[3])

    def test_call_added_kan_raises_when_tile_not_in_hand(self):
        round_state = self._create_round_state_with_pon()
        man_1m = TilesConverter.string_to_136_array(man="1111")
        round_state.players[0].tiles = TilesConverter.string_to_136_array(pin="123")

        with pytest.raises(ValueError, match="cannot call added kan"):
            call_added_kan(round_state, seat=0, tile_id=man_1m[3])


class TestCheckFourKans:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a basic round state."""
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=TilesConverter.string_to_136_array(man="1111")),
            MahjongPlayer(seat=1, name="Bot1", tiles=TilesConverter.string_to_136_array(man="2222")),
            MahjongPlayer(seat=2, name="Bot2", tiles=TilesConverter.string_to_136_array(man="3333")),
            MahjongPlayer(seat=3, name="Bot3", tiles=TilesConverter.string_to_136_array(man="4444")),
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
        round_state.players[0].melds = [self._create_kan_meld(TilesConverter.string_to_136_array(man="1111"))]
        round_state.players[1].melds = [self._create_kan_meld(TilesConverter.string_to_136_array(man="2222"))]
        round_state.players[2].melds = [self._create_kan_meld(TilesConverter.string_to_136_array(man="3333"))]

        result = check_four_kans(round_state)

        assert result is False

    def test_four_kans_by_different_players(self):
        round_state = self._create_round_state()
        round_state.players[0].melds = [self._create_kan_meld(TilesConverter.string_to_136_array(man="1111"))]
        round_state.players[1].melds = [self._create_kan_meld(TilesConverter.string_to_136_array(man="2222"))]
        round_state.players[2].melds = [self._create_kan_meld(TilesConverter.string_to_136_array(man="3333"))]
        round_state.players[3].melds = [self._create_kan_meld(TilesConverter.string_to_136_array(man="4444"))]

        result = check_four_kans(round_state)

        assert result is True

    def test_four_kans_by_two_players(self):
        round_state = self._create_round_state()
        round_state.players[0].melds = [
            self._create_kan_meld(TilesConverter.string_to_136_array(man="1111")),
            self._create_kan_meld(TilesConverter.string_to_136_array(pin="1111")),
        ]
        round_state.players[1].melds = [
            self._create_kan_meld(TilesConverter.string_to_136_array(man="2222")),
            self._create_kan_meld(TilesConverter.string_to_136_array(pin="2222")),
        ]

        result = check_four_kans(round_state)

        assert result is True

    def test_four_kans_by_one_player_no_abortive(self):
        # suukantsu is possible if one player has all 4 kans
        round_state = self._create_round_state()
        round_state.players[0].melds = [
            self._create_kan_meld(TilesConverter.string_to_136_array(man="1111")),
            self._create_kan_meld(TilesConverter.string_to_136_array(man="2222")),
            self._create_kan_meld(TilesConverter.string_to_136_array(man="3333")),
            self._create_kan_meld(TilesConverter.string_to_136_array(man="4444")),
        ]

        result = check_four_kans(round_state)

        # should NOT be abortive - one player can go for suukantsu
        assert result is False

    def test_mixed_kan_and_shouminkan(self):
        round_state = self._create_round_state()
        round_state.players[0].melds = [self._create_kan_meld(TilesConverter.string_to_136_array(man="1111"))]
        round_state.players[1].melds = [
            self._create_shouminkan_meld(TilesConverter.string_to_136_array(man="2222"))
        ]
        round_state.players[2].melds = [self._create_kan_meld(TilesConverter.string_to_136_array(man="3333"))]
        round_state.players[3].melds = [
            self._create_shouminkan_meld(TilesConverter.string_to_136_array(man="4444"))
        ]

        result = check_four_kans(round_state)

        assert result is True
