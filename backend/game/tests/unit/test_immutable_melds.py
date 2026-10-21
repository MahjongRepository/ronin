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
    resolve_added_kan_tile,
)
from game.logic.settings import GameSettings
from game.logic.tiles import tile_to_34
from game.tests.conftest import create_player, create_round_state

_DEFAULT_DEAD_WALL = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
_DEFAULT_WALL = tuple(TilesConverter.string_to_136_array(man="1111222233334444"))
_PIN_TILES = tuple(TilesConverter.string_to_136_array(pin="123456789"))


def _round_state(player0_tiles, *, player0_melds=(), current_player_seat=0, dead_wall=None):
    players = [
        create_player(seat=0, tiles=player0_tiles, melds=player0_melds),
        create_player(seat=1, tiles=TilesConverter.string_to_136_array(man="123", pin="123", sou="123456")),
        create_player(seat=2, tiles=TilesConverter.string_to_136_array(man="789", pin="789", sou="789", honors="1")),
        create_player(
            seat=3,
            tiles=TilesConverter.string_to_136_array(man="456", pin="456", sou="789", honors="2"),
            is_ippatsu=True,
        ),
    ]
    return create_round_state(
        players=players,
        wall=_DEFAULT_WALL,
        dead_wall=dead_wall or _DEFAULT_DEAD_WALL,
        dora_indicators=(_DEFAULT_DEAD_WALL[2],),
        current_player_seat=current_player_seat,
    )


class TestCallPonImmutable:
    def test_call_pon__should_add_pon_meld_and_kuikae_to_new_state(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], man_1m[1], *_PIN_TILES)
        round_state = _round_state(player0_tiles, current_player_seat=3)

        new_state, meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[2],
            settings=GameSettings(),
        )

        assert meld.type == Meld.PON
        assert len(meld.tiles) == 3
        assert meld.opened is True
        assert meld.who == 0
        assert meld.from_who == 3
        assert meld.called_tile == man_1m[2]
        assert 0 in new_state.players_with_open_hands
        assert tile_to_34(man_1m[0]) in new_state.players[0].kuikae_tiles

    def test_call_pon__should_clear_ippatsu_for_all_players(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], man_1m[1], *_PIN_TILES)
        round_state = _round_state(player0_tiles, current_player_seat=3)
        # player 3 already has ippatsu from _round_state helper
        assert round_state.players[3].is_ippatsu is True

        new_state, _meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[2],
            settings=GameSettings(),
        )

        for p in new_state.players:
            assert p.is_ippatsu is False

    def test_call_pon__when_insufficient_tiles__should_raise_invalid_meld_error(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], *_PIN_TILES)
        round_state = _round_state(player0_tiles, current_player_seat=3)

        with pytest.raises(InvalidMeldError, match="need 2 matching tiles"):
            call_pon(round_state, caller_seat=0, discarder_seat=3, tile_id=man_1m[1], settings=GameSettings())


class TestCallChiImmutable:
    def _chi_round_state(self):
        man_tiles = TilesConverter.string_to_136_array(man="123")
        player1_tiles = (man_tiles[1], man_tiles[2], *_PIN_TILES)
        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3, is_ippatsu=True),
        ]
        round_state = create_round_state(
            players=players,
            wall=_DEFAULT_WALL,
            dead_wall=_DEFAULT_DEAD_WALL,
            dora_indicators=(_DEFAULT_DEAD_WALL[2],),
            current_player_seat=0,
        )
        return round_state, man_tiles

    def test_call_chi__should_add_chi_meld_and_kuikae_to_new_state(self):
        round_state, man_tiles = self._chi_round_state()
        assert round_state.players[3].is_ippatsu is True

        new_state, meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=GameSettings(),
        )

        assert meld.type == Meld.CHI
        assert len(meld.tiles) == 3
        assert meld.opened is True
        assert meld.who == 1
        assert meld.from_who == 0
        assert meld.called_tile == man_tiles[0]
        assert len(new_state.players[1].tiles) == 9
        assert man_tiles[1] not in new_state.players[1].tiles
        assert man_tiles[2] not in new_state.players[1].tiles
        assert new_state.current_player_seat == 1
        for p in new_state.players:
            assert p.is_ippatsu is False
        assert tile_to_34(man_tiles[0]) in new_state.players[1].kuikae_tiles


class TestCallOpenKanImmutable:
    def test_call_open_kan__should_add_kan_meld_and_rinshan_state(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], man_1m[1], man_1m[2], *_PIN_TILES)
        round_state = _round_state(player0_tiles, current_player_seat=3)
        original_dead_wall_len = len(round_state.wall.dead_wall_tiles)

        new_state, meld = call_open_kan(
            round_state,
            caller_seat=0,
            discarder_seat=3,
            tile_id=man_1m[3],
            settings=GameSettings(),
        )

        assert meld.type == Meld.KAN
        assert len(meld.tiles) == 4
        assert meld.opened is True
        assert meld.who == 0
        assert meld.from_who == 3
        assert meld.called_tile == man_1m[3]
        # 12 original - 3 for kan + 1 dead wall draw = 10
        assert len(new_state.players[0].tiles) == 10
        assert len(new_state.wall.dead_wall_tiles) == original_dead_wall_len
        assert new_state.players[0].is_rinshan is True
        assert new_state.wall.pending_dora_count == 1

    def test_call_open_kan__when_insufficient_tiles__should_raise_invalid_meld_error(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], man_1m[1], *_PIN_TILES)
        round_state = _round_state(player0_tiles, current_player_seat=3)

        with pytest.raises(InvalidMeldError, match="need 3 matching tiles"):
            call_open_kan(round_state, caller_seat=0, discarder_seat=3, tile_id=man_1m[2], settings=GameSettings())


class TestCallClosedKanImmutable:
    def test_call_closed_kan__should_add_closed_kan_meld_and_reveal_dora(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (*man_1m, *_PIN_TILES)
        round_state = _round_state(player0_tiles)
        original_dora_count = len(round_state.wall.dora_indicators)

        new_state, meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=GameSettings())

        assert meld.type == Meld.KAN
        assert len(meld.tiles) == 4
        assert meld.opened is False
        assert meld.who == 0
        assert meld.from_who is None
        # 13 original - 4 for kan + 1 dead wall draw = 10
        assert len(new_state.players[0].tiles) == 10
        assert 0 not in new_state.players_with_open_hands
        assert new_state.wall.pending_dora_count == 0
        assert len(new_state.wall.dora_indicators) == original_dora_count + 1
        assert new_state.players[0].is_rinshan is True

    def test_call_closed_kan__should_clear_ippatsu_for_all_players(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (*man_1m, *_PIN_TILES)
        round_state = _round_state(player0_tiles)
        # player 3 already has ippatsu from _round_state helper
        assert round_state.players[3].is_ippatsu is True

        new_state, _meld = call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=GameSettings())

        # hand stays closed
        assert 0 not in new_state.players_with_open_hands
        # but ippatsu is cleared for everyone
        for p in new_state.players:
            assert p.is_ippatsu is False

    def test_call_closed_kan__when_insufficient_tiles__should_raise_invalid_meld_error(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], man_1m[1], man_1m[2], *_PIN_TILES)
        round_state = _round_state(player0_tiles)

        with pytest.raises(InvalidMeldError, match="need 4 matching tiles"):
            call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=GameSettings())


class TestCallAddedKanImmutable:
    def _pon_meld(self, man_1m):
        return FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(man_1m[0], man_1m[1], man_1m[2]),
            opened=True,
            called_tile=man_1m[2],
            who=0,
            from_who=3,
        )

    def test_call_added_kan__should_upgrade_pon_to_shouminkan(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = self._pon_meld(man_1m)
        player0_tiles = (man_1m[3], *_PIN_TILES)
        round_state = _round_state(player0_tiles, player0_melds=(pon_meld,))

        new_state, meld = call_added_kan(round_state, seat=0, tile_id=man_1m[3], settings=GameSettings())

        assert meld.type == Meld.SHOUMINKAN
        assert len(meld.tiles) == 4
        assert meld.opened is True
        assert meld.who == 0
        assert meld.from_who == 3
        # 10 original - 1 for kan + 1 dead wall draw = 10
        assert len(new_state.players[0].tiles) == 10
        assert man_1m[3] not in new_state.players[0].tiles
        assert len(new_state.players[0].melds) == 1
        assert new_state.players[0].melds[0].type == Meld.SHOUMINKAN
        assert new_state.wall.pending_dora_count == 1
        assert new_state.players[0].is_rinshan is True

    def test_call_added_kan__when_no_pon__should_raise_invalid_meld_error(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        player0_tiles = (man_1m[0], *_PIN_TILES)
        round_state = _round_state(player0_tiles)

        with pytest.raises(InvalidMeldError, match="no pon of tile type"):
            call_added_kan(round_state, seat=0, tile_id=man_1m[0], settings=GameSettings())

    def test_call_added_kan__when_tile_not_in_hand__should_raise_invalid_meld_error(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = self._pon_meld(man_1m)
        round_state = _round_state(_PIN_TILES, player0_melds=(pon_meld,))

        with pytest.raises(InvalidMeldError, match="not in hand"):
            call_added_kan(round_state, seat=0, tile_id=man_1m[3], settings=GameSettings())


class TestResolveAddedKanTile:
    @staticmethod
    def _pon_meld(tiles):
        return FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(tiles[:3]),
            opened=True,
            called_tile=tiles[0],
            who=0,
            from_who=3,
        )

    def test_resolve_added_kan_tile__when_no_matching_pon__should_raise_invalid_meld_error(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        round_state = _round_state((man_1m[0], *_PIN_TILES))

        with pytest.raises(InvalidMeldError, match="no pon of tile type"):
            resolve_added_kan_tile(round_state, seat=0, tile_id=man_1m[0], settings=GameSettings())

    def test_resolve_added_kan_tile__when_no_same_type_tile_in_hand__should_raise_invalid_meld_error(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = self._pon_meld(man_1m)
        round_state = _round_state(_PIN_TILES, player0_melds=(pon_meld,))

        with pytest.raises(InvalidMeldError, match="not in hand"):
            resolve_added_kan_tile(round_state, seat=0, tile_id=man_1m[3], settings=GameSettings())

    def test_resolve_added_kan_tile__when_exact_id_not_in_hand__should_use_same_type_tile(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = self._pon_meld(man_1m)
        player0_tiles = (man_1m[3], *_PIN_TILES)
        round_state = _round_state(player0_tiles, player0_melds=(pon_meld,))

        resolved = resolve_added_kan_tile(round_state, seat=0, tile_id=man_1m[2], settings=GameSettings())

        assert resolved == man_1m[3]

    def test_resolve_added_kan_tile__when_exact_id_in_hand__should_return_it(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        pon_meld = self._pon_meld(man_1m)
        player0_tiles = (man_1m[3], *_PIN_TILES)
        round_state = _round_state(player0_tiles, player0_melds=(pon_meld,))

        resolved = resolve_added_kan_tile(round_state, seat=0, tile_id=man_1m[3], settings=GameSettings())

        assert resolved == man_1m[3]


class TestFrozenMeldValidation:
    def test_frozen_meld__when_tile_count_invalid__should_be_rejected(self):
        with pytest.raises(Exception, match="3-4 tiles"):
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=(0, 1), opened=True, who=0)
        with pytest.raises(Exception, match="3-4 tiles"):
            FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(0, 1, 2, 3, 4), opened=False, who=0)

    def test_frozen_meld__when_who_invalid__should_be_rejected(self):
        with pytest.raises(Exception, match="who"):
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=(0, 1, 2), opened=True, who=-1)
        with pytest.raises(Exception, match="who"):
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=(0, 1, 2), opened=True, who=4)

    def test_frozen_meld__when_from_who_invalid__should_be_rejected(self):
        with pytest.raises(Exception, match="from_who"):
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=(0, 1, 2), opened=True, who=0, from_who=-1)
        with pytest.raises(Exception, match="from_who"):
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=(0, 1, 2), opened=True, who=0, from_who=4)
