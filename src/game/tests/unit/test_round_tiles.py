"""
Unit tests for round tile operations (draw, discard, advance turn, dora).
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.round import (
    DEAD_WALL_SIZE,
    FIRST_DORA_INDEX,
    advance_turn,
    discard_tile,
    draw_from_dead_wall,
    draw_tile,
    init_round,
    reveal_pending_dora,
)
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.tests.unit.helpers import _string_to_34_tiles


class TestDrawTile:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with wall and players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        return MahjongRoundState(
            wall=TilesConverter.string_to_136_array(man="1111222233"),
            players=players,
            current_player_seat=0,
        )

    def test_draw_tile_removes_from_wall(self):
        round_state = self._create_round_state()
        initial_wall_len = len(round_state.wall)

        draw_tile(round_state)

        assert len(round_state.wall) == initial_wall_len - 1

    def test_draw_tile_returns_first_tile(self):
        round_state = self._create_round_state()
        first_tile = round_state.wall[0]

        drawn = draw_tile(round_state)

        assert drawn == first_tile

    def test_draw_tile_adds_to_player_hand(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 2
        initial_hand_len = len(round_state.players[2].tiles)

        drawn = draw_tile(round_state)

        assert len(round_state.players[2].tiles) == initial_hand_len + 1
        assert drawn in round_state.players[2].tiles

    def test_draw_tile_appends_to_end_of_hand(self):
        round_state = self._create_round_state()
        round_state.players[0].tiles = TilesConverter.string_to_136_array(sou="888")[:3]

        drawn = draw_tile(round_state)

        assert round_state.players[0].tiles[-1] == drawn

    def test_draw_tile_returns_none_when_wall_empty(self):
        round_state = self._create_round_state()
        round_state.wall = []

        drawn = draw_tile(round_state)

        assert drawn is None

    def test_draw_tile_does_not_modify_hand_when_wall_empty(self):
        round_state = self._create_round_state()
        round_state.wall = []
        sou_88 = TilesConverter.string_to_136_array(sou="88")
        round_state.players[0].tiles = sou_88

        draw_tile(round_state)

        assert round_state.players[0].tiles == sou_88


class TestDrawFromDeadWall:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with dead wall and players for testing."""
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        # 14 tiles for dead wall: North(copies 2-3), Haku(4), Hatsu(4), Chun(4)
        dead_wall = [
            *TilesConverter.string_to_136_array(honors="4444")[2:],
            *TilesConverter.string_to_136_array(honors="555566667777"),
        ]
        # 50 tiles for live wall
        live_wall = [
            *TilesConverter.string_to_136_array(man="111122223333444455556666777788889999"),
            *TilesConverter.string_to_136_array(pin="11112222333344"),
        ]
        return MahjongRoundState(
            dead_wall=dead_wall,
            wall=live_wall,
            players=players,
            current_player_seat=0,
        )

    def test_draw_from_dead_wall_maintains_dead_wall_size(self):
        round_state = self._create_round_state()

        draw_from_dead_wall(round_state)

        # dead wall should stay at 14 (one popped, one replenished from live wall)
        assert len(round_state.dead_wall) == DEAD_WALL_SIZE

    def test_draw_from_dead_wall_returns_last_tile(self):
        round_state = self._create_round_state()
        last_tile = round_state.dead_wall[-1]

        drawn = draw_from_dead_wall(round_state)

        assert drawn == last_tile

    def test_draw_from_dead_wall_adds_to_player_hand(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 1
        initial_hand_len = len(round_state.players[1].tiles)

        drawn = draw_from_dead_wall(round_state)

        assert len(round_state.players[1].tiles) == initial_hand_len + 1
        assert drawn in round_state.players[1].tiles

    def test_draw_from_dead_wall_sets_rinshan_flag(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 0
        assert round_state.players[0].is_rinshan is False

        draw_from_dead_wall(round_state)

        assert round_state.players[0].is_rinshan is True

    def test_draw_from_dead_wall_replenishes_from_live_wall(self):
        round_state = self._create_round_state()
        initial_wall_len = len(round_state.wall)
        last_wall_tile = round_state.wall[-1]

        draw_from_dead_wall(round_state)

        # live wall loses one tile (moved to dead wall)
        assert len(round_state.wall) == initial_wall_len - 1
        # replenish tile is appended at the end of dead wall (preserves dora indicator positions at front)
        assert round_state.dead_wall[-1] == last_wall_tile

    def test_draw_from_dead_wall_without_live_wall(self):
        round_state = self._create_round_state()
        round_state.wall = []  # no live wall tiles
        initial_dead_wall_len = len(round_state.dead_wall)

        draw_from_dead_wall(round_state)

        # dead wall shrinks by 1 since no replenishment possible
        assert len(round_state.dead_wall) == initial_dead_wall_len - 1


class TestDiscardTile:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with players for testing.

        Player 0: 3m(copy2), 6m(copy0), 8m(copy2), 2p(copy0)
        Player 1: 3m(copy3), 6m(copy1), 8m(copy3), 2p(copy1)
        Player 2: 4m(copy0), 6m(copy2), 9m(copy0), 2p(copy2)
        Player 3: 4m(copy1), 6m(copy3), 9m(copy1), 2p(copy3)
        """
        man_3 = TilesConverter.string_to_136_array(man="3333")
        man_4 = TilesConverter.string_to_136_array(man="4444")
        man_6 = TilesConverter.string_to_136_array(man="6666")
        man_8 = TilesConverter.string_to_136_array(man="8888")
        man_9 = TilesConverter.string_to_136_array(man="9999")
        pin_2 = TilesConverter.string_to_136_array(pin="2222")
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[man_3[2], man_6[0], man_8[2], pin_2[0]]),
            MahjongPlayer(seat=1, name="Bot1", tiles=[man_3[3], man_6[1], man_8[3], pin_2[1]]),
            MahjongPlayer(seat=2, name="Bot2", tiles=[man_4[0], man_6[2], man_9[0], pin_2[2]]),
            MahjongPlayer(seat=3, name="Bot3", tiles=[man_4[1], man_6[3], man_9[1], pin_2[3]]),
        ]
        return MahjongRoundState(players=players, current_player_seat=0)

    def test_discard_tile_removes_from_hand(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        assert man_6 in round_state.players[0].tiles

        discard_tile(round_state, seat=0, tile_id=man_6)

        assert man_6 not in round_state.players[0].tiles

    def test_discard_tile_adds_to_discards(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        assert len(round_state.players[0].discards) == 0

        discard_tile(round_state, seat=0, tile_id=man_6)

        assert len(round_state.players[0].discards) == 1
        assert round_state.players[0].discards[0].tile_id == man_6

    def test_discard_tile_returns_discard_object(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]

        result = discard_tile(round_state, seat=0, tile_id=man_6)

        assert isinstance(result, Discard)
        assert result.tile_id == man_6

    def test_discard_tile_adds_to_all_discards(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        assert len(round_state.all_discards) == 0

        discard_tile(round_state, seat=0, tile_id=man_6)

        assert round_state.all_discards == [man_6]

    def test_discard_tile_raises_if_tile_not_in_hand(self):
        round_state = self._create_round_state()
        sou_7_copy3 = TilesConverter.string_to_136_array(sou="7777")[3]

        with pytest.raises(ValueError, match=f"tile {sou_7_copy3} not in player's hand"):
            discard_tile(round_state, seat=0, tile_id=sou_7_copy3)

    def test_discard_tile_sets_tsumogiri_for_last_tile(self):
        round_state = self._create_round_state()
        # last tile in hand (simulating just drawn)
        last_tile = round_state.players[0].tiles[-1]

        result = discard_tile(round_state, seat=0, tile_id=last_tile)

        assert result.is_tsumogiri is True

    def test_discard_tile_not_tsumogiri_for_other_tiles(self):
        round_state = self._create_round_state()
        # first tile in hand (not just drawn)
        first_tile = round_state.players[0].tiles[0]

        result = discard_tile(round_state, seat=0, tile_id=first_tile)

        assert result.is_tsumogiri is False

    def test_discard_tile_sets_riichi_flag(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]

        result = discard_tile(round_state, seat=0, tile_id=man_6, is_riichi=True)

        assert result.is_riichi_discard is True

    def test_discard_tile_clears_ippatsu_for_discarding_player_only(self):
        """Ippatsu is only cleared for the player who discards, not all players.

        Other players' ippatsu is cleared only on meld calls (pon/chi/kan).
        """
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        round_state.players[0].is_ippatsu = True
        round_state.players[1].is_ippatsu = True
        round_state.players[2].is_ippatsu = True

        discard_tile(round_state, seat=0, tile_id=man_6)

        # discarding player's ippatsu is cleared
        assert round_state.players[0].is_ippatsu is False
        # other players' ippatsu is preserved (only cleared on meld calls)
        assert round_state.players[1].is_ippatsu is True
        assert round_state.players[2].is_ippatsu is True

    def test_discard_tile_clears_rinshan_flag(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        round_state.players[0].is_rinshan = True

        discard_tile(round_state, seat=0, tile_id=man_6)

        assert round_state.players[0].is_rinshan is False

    def test_discard_tile_rejects_kuikae_forbidden_tile(self):
        round_state = self._create_round_state()
        man_3_copy2 = TilesConverter.string_to_136_array(man="333")[2]
        # 3m is tile_34=2, set kuikae to forbid it
        round_state.players[0].kuikae_tiles = _string_to_34_tiles(man="3")

        with pytest.raises(ValueError, match="forbidden by kuikae"):
            discard_tile(round_state, seat=0, tile_id=man_3_copy2)

    def test_discard_tile_allows_non_kuikae_tile(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        # forbid tile_34=2 (3m), but player discards 6m (tile_34=5, not forbidden)
        round_state.players[0].kuikae_tiles = _string_to_34_tiles(man="3")

        result = discard_tile(round_state, seat=0, tile_id=man_6)

        assert result.tile_id == man_6

    def test_discard_tile_clears_kuikae_after_discard(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        # player 0 has tiles: 3m(copy2), 6m(copy0), 8m(copy2), 2p(copy0)
        # 3m is tile_34=2, 6m is tile_34=5, 8m is tile_34=7, 2p is tile_34=10
        # set kuikae to forbid tile_34=2 (3m) and discard 6m (tile_34=5, not forbidden)
        round_state.players[0].kuikae_tiles = _string_to_34_tiles(man="3")

        discard_tile(round_state, seat=0, tile_id=man_6)

        assert round_state.players[0].kuikae_tiles == []


class TestAdvanceTurn:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state for testing."""
        return MahjongRoundState(current_player_seat=0, turn_count=0)

    def test_advance_turn_rotates_seat(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 0

        advance_turn(round_state)

        assert round_state.current_player_seat == 1

    def test_advance_turn_wraps_around(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 3

        advance_turn(round_state)

        assert round_state.current_player_seat == 0

    def test_advance_turn_increments_turn_count(self):
        round_state = self._create_round_state()
        round_state.turn_count = 5

        advance_turn(round_state)

        assert round_state.turn_count == 6

    def test_advance_turn_returns_new_seat(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 1

        result = advance_turn(round_state)

        assert result == 2

    def test_advance_turn_full_rotation(self):
        round_state = self._create_round_state()
        round_state.current_player_seat = 0

        for expected_seat in [1, 2, 3, 0]:
            result = advance_turn(round_state)
            assert result == expected_seat


class TestRevealPendingDora:
    def _create_round_state_with_pending_dora(self, pending_count: int = 1) -> MahjongRoundState:
        """Create a round state with pending dora indicators."""
        # 14 tiles: North(copies 2-3), Haku(4), Hatsu(4), Chun(4)
        dead_wall = [
            *TilesConverter.string_to_136_array(honors="4444")[2:],
            *TilesConverter.string_to_136_array(honors="555566667777"),
        ]
        return MahjongRoundState(
            dead_wall=dead_wall,
            dora_indicators=[dead_wall[FIRST_DORA_INDEX]],
            pending_dora_count=pending_count,
        )

    def test_reveal_pending_dora_adds_indicator(self):
        round_state = self._create_round_state_with_pending_dora(pending_count=1)
        initial_dora_count = len(round_state.dora_indicators)

        reveal_pending_dora(round_state)

        assert len(round_state.dora_indicators) == initial_dora_count + 1
        assert round_state.pending_dora_count == 0

    def test_reveal_pending_dora_multiple(self):
        round_state = self._create_round_state_with_pending_dora(pending_count=2)
        initial_dora_count = len(round_state.dora_indicators)

        reveal_pending_dora(round_state)

        assert len(round_state.dora_indicators) == initial_dora_count + 2
        assert round_state.pending_dora_count == 0

    def test_reveal_pending_dora_noop_when_zero(self):
        round_state = self._create_round_state_with_pending_dora(pending_count=0)
        initial_dora_count = len(round_state.dora_indicators)

        reveal_pending_dora(round_state)

        assert len(round_state.dora_indicators) == initial_dora_count
        assert round_state.pending_dora_count == 0


class TestDiscardTileRevealsPendingDora:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with pending dora and dead wall."""
        # 14 tiles: North(copies 2-3), Haku(4), Hatsu(4), Chun(4)
        dead_wall = [
            *TilesConverter.string_to_136_array(honors="4444")[2:],
            *TilesConverter.string_to_136_array(honors="555566667777"),
        ]
        man_3 = TilesConverter.string_to_136_array(man="3333")
        man_4 = TilesConverter.string_to_136_array(man="4444")
        man_6 = TilesConverter.string_to_136_array(man="6666")
        man_8 = TilesConverter.string_to_136_array(man="8888")
        man_9 = TilesConverter.string_to_136_array(man="9999")
        pin_2 = TilesConverter.string_to_136_array(pin="2222")
        players = [
            MahjongPlayer(seat=0, name="Player1", tiles=[man_3[2], man_6[0], man_8[2], pin_2[0]]),
            MahjongPlayer(seat=1, name="Bot1", tiles=[man_3[3], man_6[1], man_8[3], pin_2[1]]),
            MahjongPlayer(seat=2, name="Bot2", tiles=[man_4[0], man_6[2], man_9[0], pin_2[2]]),
            MahjongPlayer(seat=3, name="Bot3", tiles=[man_4[1], man_6[3], man_9[1], pin_2[3]]),
        ]
        return MahjongRoundState(
            players=players,
            current_player_seat=0,
            dead_wall=dead_wall,
            dora_indicators=[dead_wall[FIRST_DORA_INDEX]],
            pending_dora_count=1,
        )

    def test_discard_reveals_pending_dora(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        initial_dora_count = len(round_state.dora_indicators)

        discard_tile(round_state, seat=0, tile_id=man_6)

        assert len(round_state.dora_indicators) == initial_dora_count + 1
        assert round_state.pending_dora_count == 0

    def test_discard_reveals_multiple_pending_dora(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        round_state.pending_dora_count = 2
        initial_dora_count = len(round_state.dora_indicators)

        discard_tile(round_state, seat=0, tile_id=man_6)

        assert len(round_state.dora_indicators) == initial_dora_count + 2
        assert round_state.pending_dora_count == 0

    def test_discard_without_pending_dora_unchanged(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        round_state.pending_dora_count = 0
        initial_dora_count = len(round_state.dora_indicators)

        discard_tile(round_state, seat=0, tile_id=man_6)

        assert len(round_state.dora_indicators) == initial_dora_count
        assert round_state.pending_dora_count == 0


class TestInitRoundResetsPendingDora:
    def test_init_round_resets_pending_dora_count(self):
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        ]
        round_state = MahjongRoundState(players=players, dealer_seat=0, pending_dora_count=2)
        game_state = MahjongGameState(round_state=round_state, seed=12345.0, round_number=0)

        init_round(game_state)

        assert game_state.round_state.pending_dora_count == 0
