"""
Unit tests for immutable round tile operations (draw, discard, advance turn, dora).
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.round import (
    DEAD_WALL_SIZE,
    FIRST_DORA_INDEX,
    add_dora_indicator,
    discard_tile,
    draw_from_dead_wall,
    draw_tile,
    reveal_pending_dora,
)
from game.logic.state import (
    MahjongPlayer,
    MahjongRoundState,
)
from game.tests.unit.helpers import _string_to_34_tiles


class TestDrawTileImmutable:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with wall and players for testing."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}" if i == 0 else f"Bot{i}") for i in range(4))
        return MahjongRoundState(
            wall=tuple(TilesConverter.string_to_136_array(man="1111222233")),
            players=players,
            current_player_seat=0,
        )

    def test_draw_tile_appends_to_end_of_hand(self):
        """Drawn tile must be last in hand; tsumogiri detection relies on this."""
        round_state = self._create_round_state()
        starting_tiles = tuple(TilesConverter.string_to_136_array(sou="888")[:3])
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"tiles": starting_tiles})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        new_state, drawn = draw_tile(round_state)

        assert new_state.players[0].tiles[-1] == drawn

    def test_draw_from_empty_wall_returns_none(self):
        """Drawing from an empty wall returns the unchanged state and None."""
        round_state = self._create_round_state()
        round_state = round_state.model_copy(update={"wall": ()})

        result_state, drawn = draw_tile(round_state)

        assert drawn is None
        assert result_state is round_state


class TestDrawFromDeadWallImmutable:
    def _create_round_state(self) -> MahjongRoundState:
        """Create a round state with dead wall and players for testing."""
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}" if i == 0 else f"Bot{i}") for i in range(4))
        # 14 tiles for dead wall: North(copies 2-3), Haku(4), Hatsu(4), Chun(4)
        dead_wall = (
            *TilesConverter.string_to_136_array(honors="4444")[2:],
            *TilesConverter.string_to_136_array(honors="555566667777"),
        )
        # 50 tiles for live wall
        live_wall = (
            *TilesConverter.string_to_136_array(man="111122223333444455556666777788889999"),
            *TilesConverter.string_to_136_array(pin="11112222333344"),
        )
        return MahjongRoundState(
            dead_wall=dead_wall,
            wall=live_wall,
            players=players,
            current_player_seat=0,
        )

    def test_draw_from_dead_wall_maintains_dead_wall_size(self):
        round_state = self._create_round_state()

        new_state, _drawn = draw_from_dead_wall(round_state)

        # dead wall should stay at 14 (one popped, one replenished from live wall)
        assert len(new_state.dead_wall) == DEAD_WALL_SIZE
        # original state unchanged
        assert len(round_state.dead_wall) == DEAD_WALL_SIZE

    def test_draw_from_dead_wall_returns_last_tile(self):
        round_state = self._create_round_state()
        last_tile = round_state.dead_wall[-1]

        _new_state, drawn = draw_from_dead_wall(round_state)

        assert drawn == last_tile

    def test_draw_from_dead_wall_adds_to_player_hand(self):
        round_state = self._create_round_state()
        round_state = round_state.model_copy(update={"current_player_seat": 1})
        initial_hand_len = len(round_state.players[1].tiles)

        new_state, drawn = draw_from_dead_wall(round_state)

        assert len(new_state.players[1].tiles) == initial_hand_len + 1
        assert drawn in new_state.players[1].tiles
        # original state unchanged
        assert len(round_state.players[1].tiles) == initial_hand_len

    def test_draw_from_dead_wall_sets_rinshan_flag(self):
        round_state = self._create_round_state()
        assert round_state.players[0].is_rinshan is False

        new_state, _drawn = draw_from_dead_wall(round_state)

        assert new_state.players[0].is_rinshan is True
        # original state unchanged
        assert round_state.players[0].is_rinshan is False

    def test_draw_from_dead_wall_replenishes_from_live_wall(self):
        round_state = self._create_round_state()
        initial_wall_len = len(round_state.wall)
        last_wall_tile = round_state.wall[-1]

        new_state, _drawn = draw_from_dead_wall(round_state)

        # live wall loses one tile (moved to dead wall)
        assert len(new_state.wall) == initial_wall_len - 1
        # replenish tile is appended at the end of dead wall
        assert new_state.dead_wall[-1] == last_wall_tile
        # original state unchanged
        assert len(round_state.wall) == initial_wall_len

    def test_draw_from_dead_wall_without_live_wall(self):
        round_state = self._create_round_state()
        round_state = round_state.model_copy(update={"wall": ()})  # no live wall tiles
        initial_dead_wall_len = len(round_state.dead_wall)

        new_state, _drawn = draw_from_dead_wall(round_state)

        # dead wall shrinks by 1 since no replenishment possible
        assert len(new_state.dead_wall) == initial_dead_wall_len - 1


class TestDiscardTileImmutable:
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
        players = (
            MahjongPlayer(seat=0, name="Player1", tiles=(man_3[2], man_6[0], man_8[2], pin_2[0])),
            MahjongPlayer(seat=1, name="Bot1", tiles=(man_3[3], man_6[1], man_8[3], pin_2[1])),
            MahjongPlayer(seat=2, name="Bot2", tiles=(man_4[0], man_6[2], man_9[0], pin_2[2])),
            MahjongPlayer(seat=3, name="Bot3", tiles=(man_4[1], man_6[3], man_9[1], pin_2[3])),
        )
        return MahjongRoundState(players=players, current_player_seat=0)

    def test_discard_tile_raises_if_tile_not_in_hand(self):
        round_state = self._create_round_state()
        sou_7_copy3 = TilesConverter.string_to_136_array(sou="7777")[3]

        with pytest.raises(ValueError, match=f"tile {sou_7_copy3} not in player's hand"):
            discard_tile(round_state, seat=0, tile_id=sou_7_copy3)

    def test_discard_tile_sets_tsumogiri_for_last_tile(self):
        round_state = self._create_round_state()
        # last tile in hand (simulating just drawn)
        last_tile = round_state.players[0].tiles[-1]

        _new_state, result = discard_tile(round_state, seat=0, tile_id=last_tile)

        assert result.is_tsumogiri is True

    def test_discard_tile_not_tsumogiri_for_other_tiles(self):
        round_state = self._create_round_state()
        # first tile in hand (not just drawn)
        first_tile = round_state.players[0].tiles[0]

        _new_state, result = discard_tile(round_state, seat=0, tile_id=first_tile)

        assert result.is_tsumogiri is False

    def test_discard_tile_sets_riichi_flag(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]

        _new_state, result = discard_tile(round_state, seat=0, tile_id=man_6, is_riichi=True)

        assert result.is_riichi_discard is True

    def test_discard_tile_clears_ippatsu_for_discarding_player_only(self):
        """Ippatsu is only cleared for the player who discards, not all players."""
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"is_ippatsu": True})
        players[1] = players[1].model_copy(update={"is_ippatsu": True})
        players[2] = players[2].model_copy(update={"is_ippatsu": True})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        new_state, _discard = discard_tile(round_state, seat=0, tile_id=man_6)

        # discarding player's ippatsu is cleared
        assert new_state.players[0].is_ippatsu is False
        # other players' ippatsu is preserved (only cleared on meld calls)
        assert new_state.players[1].is_ippatsu is True
        assert new_state.players[2].is_ippatsu is True
        # original state unchanged
        assert round_state.players[0].is_ippatsu is True

    def test_discard_tile_clears_rinshan_flag(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"is_rinshan": True})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        new_state, _discard = discard_tile(round_state, seat=0, tile_id=man_6)

        assert new_state.players[0].is_rinshan is False
        # original state unchanged
        assert round_state.players[0].is_rinshan is True

    def test_discard_tile_rejects_kuikae_forbidden_tile(self):
        round_state = self._create_round_state()
        man_3_copy2 = TilesConverter.string_to_136_array(man="333")[2]
        # 3m is tile_34=2, set kuikae to forbid it
        kuikae = tuple(_string_to_34_tiles(man="3"))
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"kuikae_tiles": kuikae})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        with pytest.raises(ValueError, match="forbidden by kuikae"):
            discard_tile(round_state, seat=0, tile_id=man_3_copy2)

    def test_discard_tile_allows_non_kuikae_tile(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        # forbid tile_34=2 (3m), but player discards 6m (tile_34=5, not forbidden)
        kuikae = tuple(_string_to_34_tiles(man="3"))
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"kuikae_tiles": kuikae})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        _new_state, result = discard_tile(round_state, seat=0, tile_id=man_6)

        assert result.tile_id == man_6

    def test_discard_tile_clears_kuikae_after_discard(self):
        round_state = self._create_round_state()
        man_6 = TilesConverter.string_to_136_array(man="6")[0]
        kuikae = tuple(_string_to_34_tiles(man="3"))
        players = list(round_state.players)
        players[0] = players[0].model_copy(update={"kuikae_tiles": kuikae})
        round_state = round_state.model_copy(update={"players": tuple(players)})

        new_state, _discard = discard_tile(round_state, seat=0, tile_id=man_6)

        assert new_state.players[0].kuikae_tiles == ()
        # original state unchanged
        assert round_state.players[0].kuikae_tiles == kuikae


class TestAddDoraIndicatorImmutable:
    def _create_round_state_with_dora(self, dora_count: int = 1) -> MahjongRoundState:
        """Create a round state with dora indicators for testing."""
        dead_wall = (
            *TilesConverter.string_to_136_array(honors="4444")[2:],
            *TilesConverter.string_to_136_array(honors="555566667777"),
        )
        # initial dora indicators (first one is at index 2)
        dora_indicators = tuple(dead_wall[FIRST_DORA_INDEX : FIRST_DORA_INDEX + dora_count])
        return MahjongRoundState(
            dead_wall=dead_wall,
            dora_indicators=dora_indicators,
        )

    def test_add_dora_indicator_adds_indicator(self):
        round_state = self._create_round_state_with_dora(dora_count=1)
        initial_dora_count = len(round_state.dora_indicators)

        new_state, new_indicator = add_dora_indicator(round_state)

        assert len(new_state.dora_indicators) == initial_dora_count + 1
        assert new_indicator == new_state.dora_indicators[-1]
        # original state unchanged
        assert len(round_state.dora_indicators) == initial_dora_count

    def test_add_dora_indicator_correct_index(self):
        round_state = self._create_round_state_with_dora(dora_count=2)
        # next dora should be at index 4 (FIRST_DORA_INDEX + 2)
        expected_indicator = round_state.dead_wall[4]

        _new_state, new_indicator = add_dora_indicator(round_state)

        assert new_indicator == expected_indicator

    def test_add_dora_indicator_raises_at_max(self):
        round_state = self._create_round_state_with_dora(dora_count=5)

        with pytest.raises(ValueError, match="cannot add more than 5 dora indicators"):
            add_dora_indicator(round_state)


class TestRevealPendingDoraImmutable:
    def _create_round_state_with_pending_dora(self, pending_count: int = 1) -> MahjongRoundState:
        """Create a round state with pending dora indicators."""
        dead_wall = (
            *TilesConverter.string_to_136_array(honors="4444")[2:],
            *TilesConverter.string_to_136_array(honors="555566667777"),
        )
        return MahjongRoundState(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[FIRST_DORA_INDEX],),
            pending_dora_count=pending_count,
        )

    def test_reveal_pending_dora_adds_indicator(self):
        round_state = self._create_round_state_with_pending_dora(pending_count=1)
        initial_dora_count = len(round_state.dora_indicators)

        new_state, revealed = reveal_pending_dora(round_state)

        assert len(new_state.dora_indicators) == initial_dora_count + 1
        assert new_state.pending_dora_count == 0
        assert len(revealed) == 1
        assert revealed[0] == new_state.dora_indicators[-1]
        # original state unchanged
        assert len(round_state.dora_indicators) == initial_dora_count
        assert round_state.pending_dora_count == 1

    def test_reveal_pending_dora_multiple(self):
        round_state = self._create_round_state_with_pending_dora(pending_count=2)
        initial_dora_count = len(round_state.dora_indicators)

        new_state, revealed = reveal_pending_dora(round_state)

        assert len(new_state.dora_indicators) == initial_dora_count + 2
        assert new_state.pending_dora_count == 0
        assert len(revealed) == 2
        # verify ordering: revealed in the same order as added to dora_indicators
        assert revealed[0] == new_state.dora_indicators[-2]
        assert revealed[1] == new_state.dora_indicators[-1]
        # original state unchanged
        assert len(round_state.dora_indicators) == initial_dora_count

    def test_reveal_pending_dora_noop_when_zero(self):
        round_state = self._create_round_state_with_pending_dora(pending_count=0)
        initial_dora_count = len(round_state.dora_indicators)

        new_state, revealed = reveal_pending_dora(round_state)

        assert len(new_state.dora_indicators) == initial_dora_count
        assert new_state.pending_dora_count == 0
        assert revealed == []
