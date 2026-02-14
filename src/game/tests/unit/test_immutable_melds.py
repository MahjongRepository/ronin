"""
Unit tests for immutable meld operations.
"""

import pytest
from mahjong.meld import Meld
from mahjong.tile import TilesConverter

from game.logic.exceptions import InvalidMeldError
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import (
    call_added_kan,
    call_chi,
    call_closed_kan,
    call_open_kan,
    call_pon,
)
from game.logic.settings import GameSettings
from game.logic.state import (
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.tiles import tile_to_34


def _create_frozen_players(
    player0_tiles: tuple[int, ...] | None = None,
    player0_melds: tuple[FrozenMeld, ...] = (),
) -> tuple[MahjongPlayer, ...]:
    """Create a tuple of frozen players for testing."""
    if player0_tiles is None:
        player0_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="111"))
    return (
        MahjongPlayer(
            seat=0,
            name="Player0",
            tiles=player0_tiles,
            melds=player0_melds,
            score=25000,
        ),
        MahjongPlayer(
            seat=1,
            name="AI1",
            tiles=tuple(TilesConverter.string_to_136_array(man="123", pin="123", sou="123456")),
            score=25000,
        ),
        MahjongPlayer(
            seat=2,
            name="AI2",
            tiles=tuple(TilesConverter.string_to_136_array(man="789", pin="789", sou="789", honors="1")),
            score=25000,
        ),
        MahjongPlayer(
            seat=3,
            name="AI3",
            tiles=tuple(TilesConverter.string_to_136_array(man="456", pin="456", sou="789", honors="2")),
            score=25000,
            is_ippatsu=True,  # to verify ippatsu clearing
        ),
    )


def _create_frozen_round_state(  # noqa: PLR0913
    players: tuple[MahjongPlayer, ...] | None = None,
    wall: tuple[int, ...] | None = None,
    dead_wall: tuple[int, ...] | None = None,
    current_player_seat: int = 0,
    pending_dora_count: int = 0,
    players_with_open_hands: tuple[int, ...] = (),
) -> MahjongRoundState:
    """Create a frozen round state for testing."""
    if players is None:
        players = _create_frozen_players()
    if wall is None:
        wall = tuple(TilesConverter.string_to_136_array(man="1111222233334444"))
    if dead_wall is None:
        # 14 tiles for dead wall
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))

    return MahjongRoundState(
        wall=wall,
        dead_wall=dead_wall,
        dora_indicators=(dead_wall[2],) if dead_wall else (),
        players=players,
        dealer_seat=0,
        current_player_seat=current_player_seat,
        round_wind=0,
        turn_count=0,
        all_discards=(),
        players_with_open_hands=players_with_open_hands,
        pending_dora_count=pending_dora_count,
    )


class TestCallPonImmutable:
    def test_call_pon_creates_correct_meld(self):
        """Test that call_pon creates a proper pon meld."""
        # Player 0 has two 1m tiles
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], man_1m[1], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=3)

        # Player 3 discards 1m, player 0 calls pon
        settings = GameSettings()
        _new_state, meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[2],
            settings=settings,
        )

        # Verify meld properties
        assert meld.type == Meld.PON
        assert len(meld.tiles) == 3
        assert meld.opened is True
        assert meld.who == 0
        assert meld.from_who == 3
        assert meld.called_tile == man_1m[2]

    def test_call_pon_adds_to_open_hands(self):
        """Test that caller is added to players_with_open_hands."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], man_1m[1], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=3)

        settings = GameSettings()
        new_state, _meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[2],
            settings=settings,
        )

        assert 0 in new_state.players_with_open_hands

    def test_call_pon_sets_kuikae_restriction(self):
        """Test that kuikae restriction is set correctly."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], man_1m[1], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=3)

        settings = GameSettings()
        new_state, _meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[2],
            settings=settings,
        )

        # Kuikae should forbid 1m (tile_34 = 0)
        assert tile_to_34(man_1m[0]) in new_state.players[0].kuikae_tiles

    def test_call_pon_raises_on_insufficient_tiles(self):
        """Test that ValueError is raised when not enough matching tiles."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        # Only one 1m tile
        player0_tiles = (man_1m[0], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=3)

        settings = GameSettings()
        with pytest.raises(InvalidMeldError, match="need 2 matching tiles"):
            call_pon(round_state, caller_seat=0, discarder_seat=3, tile_id=man_1m[1], settings=settings)


class TestCallChiImmutable:
    def test_call_chi_creates_correct_meld(self):
        """Test that call_chi creates a proper chi meld."""
        # Player 1 has 2m, 3m tiles (can chi 1m)
        man_tiles = TilesConverter.string_to_136_array(man="123")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player1_tiles = (man_tiles[1], man_tiles[2], *pin_tiles)

        players = list(_create_frozen_players())
        players[1] = players[1].model_copy(update={"tiles": player1_tiles})
        round_state = _create_frozen_round_state(
            players=tuple(players),
            current_player_seat=0,
        )

        # Player 0 discards 1m, player 1 (kamicha) calls chi with 2m, 3m
        settings = GameSettings()
        _new_state, meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        # Verify meld properties
        assert meld.type == Meld.CHI
        assert len(meld.tiles) == 3
        assert meld.opened is True
        assert meld.who == 1
        assert meld.from_who == 0
        assert meld.called_tile == man_tiles[0]

    def test_call_chi_removes_sequence_tiles_from_hand(self):
        """Test that sequence tiles are removed from caller's hand."""
        man_tiles = TilesConverter.string_to_136_array(man="123")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player1_tiles = (man_tiles[1], man_tiles[2], *pin_tiles)

        players = list(_create_frozen_players())
        players[1] = players[1].model_copy(update={"tiles": player1_tiles})
        round_state = _create_frozen_round_state(
            players=tuple(players),
            current_player_seat=0,
        )

        settings = GameSettings()
        new_state, _meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        # Verify sequence tiles removed
        assert len(new_state.players[1].tiles) == 9  # 11 - 2 = 9
        assert man_tiles[1] not in new_state.players[1].tiles
        assert man_tiles[2] not in new_state.players[1].tiles

    def test_call_chi_sets_current_player_to_caller(self):
        """Test that current player is set to the caller."""
        man_tiles = TilesConverter.string_to_136_array(man="123")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player1_tiles = (man_tiles[1], man_tiles[2], *pin_tiles)

        players = list(_create_frozen_players())
        players[1] = players[1].model_copy(update={"tiles": player1_tiles})
        round_state = _create_frozen_round_state(
            players=tuple(players),
            current_player_seat=0,
        )

        settings = GameSettings()
        new_state, _meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        assert new_state.current_player_seat == 1

    def test_call_chi_clears_ippatsu_for_all_players(self):
        """Test that ippatsu is cleared for all players."""
        man_tiles = TilesConverter.string_to_136_array(man="123")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player1_tiles = (man_tiles[1], man_tiles[2], *pin_tiles)

        players = list(_create_frozen_players())
        players[1] = players[1].model_copy(update={"tiles": player1_tiles})
        round_state = _create_frozen_round_state(
            players=tuple(players),
            current_player_seat=0,
        )

        # Player 3 has is_ippatsu=True in the helper
        assert round_state.players[3].is_ippatsu is True

        settings = GameSettings()
        new_state, _meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        for p in new_state.players:
            assert p.is_ippatsu is False

    def test_call_chi_sets_kuikae_restriction(self):
        """Test that kuikae restriction is set correctly for chi."""
        man_tiles = TilesConverter.string_to_136_array(man="123")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player1_tiles = (man_tiles[1], man_tiles[2], *pin_tiles)

        players = list(_create_frozen_players())
        players[1] = players[1].model_copy(update={"tiles": player1_tiles})
        round_state = _create_frozen_round_state(
            players=tuple(players),
            current_player_seat=0,
        )

        settings = GameSettings()
        new_state, _meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        # Kuikae forbids 1m (called tile)
        assert tile_to_34(man_tiles[0]) in new_state.players[1].kuikae_tiles


class TestCallOpenKanImmutable:
    def test_call_open_kan_creates_correct_meld(self):
        """Test that call_open_kan creates a proper open kan meld."""
        # Player 0 has three 1m tiles
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (man_1m[0], man_1m[1], man_1m[2], *pin_tiles)
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=3)

        settings = GameSettings()
        _new_state, meld = call_open_kan(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[3],
            settings=settings,
        )

        # Verify meld properties
        assert meld.type == Meld.KAN
        assert len(meld.tiles) == 4
        assert meld.opened is True
        assert meld.who == 0
        assert meld.from_who == 3
        assert meld.called_tile == man_1m[3]

    def test_call_open_kan_removes_tiles_from_hand(self):
        """Test that 3 tiles are removed from caller's hand."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        other_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (man_1m[0], man_1m[1], man_1m[2], *other_tiles)
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=3)

        settings = GameSettings()
        new_state, _meld = call_open_kan(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[3],
            settings=settings,
        )

        # Hand should have 9 (pin) + 1 (drawn from dead wall) = 10 tiles
        # But 3 removed for kan, so 9 + 1 = 10
        assert len(new_state.players[0].tiles) == 10  # 12 - 3 + 1 (dead wall draw)

    def test_call_open_kan_draws_from_dead_wall(self):
        """Test that a tile is drawn from dead wall."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (
            man_1m[0],
            man_1m[1],
            man_1m[2],
            *TilesConverter.string_to_136_array(pin="123456789"),
        )
        players = _create_frozen_players(player0_tiles=player0_tiles)

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = _create_frozen_round_state(players=players, current_player_seat=3, dead_wall=dead_wall)

        original_dead_wall_len = len(round_state.dead_wall)

        settings = GameSettings()
        new_state, _meld = call_open_kan(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[3],
            settings=settings,
        )

        # Dead wall should maintain same size (replenished from live wall)
        assert len(new_state.dead_wall) == original_dead_wall_len

    def test_call_open_kan_sets_rinshan_flag(self):
        """Test that is_rinshan flag is set."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (
            man_1m[0],
            man_1m[1],
            man_1m[2],
            *TilesConverter.string_to_136_array(pin="123456789"),
        )
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=3)

        settings = GameSettings()
        new_state, _meld = call_open_kan(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[3],
            settings=settings,
        )

        assert new_state.players[0].is_rinshan is True

    def test_call_open_kan_sets_pending_dora(self):
        """Test that pending_dora_count is incremented (open kan defers dora reveal)."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (
            man_1m[0],
            man_1m[1],
            man_1m[2],
            *TilesConverter.string_to_136_array(pin="123456789"),
        )
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=3)

        settings = GameSettings()
        new_state, _meld = call_open_kan(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[3],
            settings=settings,
        )

        assert new_state.pending_dora_count == 1

    def test_call_open_kan_raises_on_insufficient_tiles(self):
        """Test that ValueError is raised when not enough matching tiles."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        # Only two 1m tiles
        player0_tiles = (man_1m[0], man_1m[1], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=3)

        settings = GameSettings()
        with pytest.raises(InvalidMeldError, match="need 3 matching tiles"):
            call_open_kan(round_state, caller_seat=0, discarder_seat=3, tile_id=man_1m[2], settings=settings)


class TestCallClosedKanImmutable:
    def test_call_closed_kan_creates_correct_meld(self):
        """Test that call_closed_kan creates a proper closed kan meld."""
        # Player 0 has four 1m tiles
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (*man_1m, *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        _new_state, meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)

        # Verify meld properties
        assert meld.type == Meld.KAN
        assert len(meld.tiles) == 4
        assert meld.opened is False  # Closed kan
        assert meld.who == 0
        assert meld.from_who is None  # No from_who for closed kan

    def test_call_closed_kan_removes_tiles_from_hand(self):
        """Test that 4 tiles are removed from caller's hand."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        other_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (*man_1m, *other_tiles)
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        new_state, _meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)

        # Hand should have 9 (pin) + 1 (dead wall draw) = 10 tiles
        assert len(new_state.players[0].tiles) == 10

    def test_call_closed_kan_does_not_open_hand(self):
        """Test that closed kan does not add to players_with_open_hands."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (*man_1m, *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        new_state, _meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)

        assert 0 not in new_state.players_with_open_hands

    def test_call_closed_kan_reveals_dora_immediately(self):
        """Test that closed kan reveals dora immediately (not pending)."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (*man_1m, *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)

        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
        round_state = _create_frozen_round_state(
            players=players,
            current_player_seat=0,
            dead_wall=dead_wall,
        )

        original_dora_count = len(round_state.dora_indicators)

        settings = GameSettings()
        new_state, _meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)

        # Dora revealed immediately (not pending)
        assert new_state.pending_dora_count == 0
        assert len(new_state.dora_indicators) == original_dora_count + 1

    def test_call_closed_kan_sets_rinshan_flag(self):
        """Test that is_rinshan flag is set."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (*man_1m, *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        new_state, _meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)

        assert new_state.players[0].is_rinshan is True

    def test_call_closed_kan_raises_on_insufficient_tiles(self):
        """Test that ValueError is raised when not enough matching tiles."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        # Only three 1m tiles
        player0_tiles = (
            man_1m[0],
            man_1m[1],
            man_1m[2],
            *TilesConverter.string_to_136_array(pin="123456789"),
        )
        players = _create_frozen_players(player0_tiles=player0_tiles)
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        with pytest.raises(InvalidMeldError, match="need 4 matching tiles"):
            call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)


class TestCallAddedKanImmutable:
    def test_call_added_kan_creates_correct_meld(self):
        """Test that call_added_kan creates a proper shouminkan meld."""
        # Player 0 has a pon of 1m and the 4th 1m in hand
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(man_1m[0], man_1m[1], man_1m[2]),
            opened=True,
            called_tile=man_1m[2],
            who=0,
            from_who=3,
        )
        player0_tiles = (man_1m[3], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles, player0_melds=(pon_meld,))
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        _new_state, meld = call_added_kan(round_state, seat=0, tile_id=man_1m[3], settings=settings)

        # Verify meld properties
        assert meld.type == Meld.SHOUMINKAN
        assert len(meld.tiles) == 4
        assert meld.opened is True
        assert meld.who == 0
        assert meld.from_who == 3  # Preserved from original pon

    def test_call_added_kan_removes_tile_from_hand(self):
        """Test that the 4th tile is removed from hand."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(man_1m[0], man_1m[1], man_1m[2]),
            opened=True,
            called_tile=man_1m[2],
            who=0,
            from_who=3,
        )
        other_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player0_tiles = (man_1m[3], *other_tiles)
        players = _create_frozen_players(player0_tiles=player0_tiles, player0_melds=(pon_meld,))
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        new_state, _meld = call_added_kan(round_state, seat=0, tile_id=man_1m[3], settings=settings)

        # Hand should have 9 (pin) + 1 (dead wall draw) = 10 tiles
        assert len(new_state.players[0].tiles) == 10
        # 4th 1m should be gone from hand (now in meld)
        assert man_1m[3] not in new_state.players[0].tiles

    def test_call_added_kan_replaces_pon_with_kan(self):
        """Test that the pon meld is replaced with a kan meld."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(man_1m[0], man_1m[1], man_1m[2]),
            opened=True,
            called_tile=man_1m[2],
            who=0,
            from_who=3,
        )
        player0_tiles = (man_1m[3], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles, player0_melds=(pon_meld,))
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        new_state, _meld = call_added_kan(round_state, seat=0, tile_id=man_1m[3], settings=settings)

        # Should still have 1 meld, but it's now a shouminkan
        assert len(new_state.players[0].melds) == 1
        assert new_state.players[0].melds[0].type == Meld.SHOUMINKAN

    def test_call_added_kan_sets_pending_dora(self):
        """Test that pending_dora_count is incremented (added kan defers dora reveal)."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(man_1m[0], man_1m[1], man_1m[2]),
            opened=True,
            called_tile=man_1m[2],
            who=0,
            from_who=3,
        )
        player0_tiles = (man_1m[3], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles, player0_melds=(pon_meld,))
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        new_state, _meld = call_added_kan(round_state, seat=0, tile_id=man_1m[3], settings=settings)

        assert new_state.pending_dora_count == 1

    def test_call_added_kan_raises_on_no_pon(self):
        """Test that ValueError is raised when no pon exists to upgrade."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles)  # No melds
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        with pytest.raises(InvalidMeldError, match="no pon of tile type"):
            call_added_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)

    def test_call_added_kan_raises_on_tile_not_in_hand(self):
        """Test that InvalidMeldError is raised when 4th tile is not in hand."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(man_1m[0], man_1m[1], man_1m[2]),
            opened=True,
            called_tile=man_1m[2],
            who=0,
            from_who=3,
        )
        # 4th 1m NOT in hand
        player0_tiles = tuple(TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles, player0_melds=(pon_meld,))
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        with pytest.raises(InvalidMeldError, match="not in hand"):
            call_added_kan(round_state, seat=0, tile_id=man_1m[3], settings=settings)

    def test_call_added_kan_sets_rinshan_flag(self):
        """Test that is_rinshan flag is set."""
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(man_1m[0], man_1m[1], man_1m[2]),
            opened=True,
            called_tile=man_1m[2],
            who=0,
            from_who=3,
        )
        player0_tiles = (man_1m[3], *TilesConverter.string_to_136_array(pin="123456789"))
        players = _create_frozen_players(player0_tiles=player0_tiles, player0_melds=(pon_meld,))
        round_state = _create_frozen_round_state(players=players, current_player_seat=0)

        settings = GameSettings()
        new_state, _meld = call_added_kan(round_state, seat=0, tile_id=man_1m[3], settings=settings)

        assert new_state.players[0].is_rinshan is True
