import pytest
from mahjong.tile import TilesConverter

from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import MeldCallType
from game.logic.exceptions import InvalidMeldError
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import (
    _check_pao,
    _validate_chi_sequence,
    call_chi,
    can_call_open_kan,
    get_kuikae_tiles,
    get_possible_added_kans,
    get_possible_closed_kans,
)
from game.logic.runtime import GameRuntime
from game.logic.settings import GameSettings
from game.logic.state import Discard, MahjongPlayer, MahjongRoundState
from game.logic.tiles import tile_to_34
from game.tests.conftest import create_dealt_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies
from game.tests.unit.helpers import _update_round_state


class TestKuikaeEdgeCases:
    def test_get_kuikae_tiles__when_called_tile_is_highest__should_forbid_called_tile_and_low_suji(self):
        # Create sequence 123m where called_tile is 3m (tile_34=2 in man suit)
        man_tiles = TilesConverter.string_to_136_array(man="123")
        called_tile_34 = tile_to_34(man_tiles[2])  # 3m is tile_34 = 2
        sequence_tiles_34 = [tile_to_34(man_tiles[0]), tile_to_34(man_tiles[1])]  # 1m, 2m

        forbidden = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_tile_34, sequence_tiles_34=sequence_tiles_34
        )
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

        forbidden_234 = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_tile_34_4m, sequence_tiles_34=sequence_tiles_34_23
        )
        # Sequence is [1, 2, 3] (234m in tile_34), called is 3 (4m)
        # suji = all_tiles[0] - 1 = 1 - 1 = 0 (1m)
        assert called_tile_34_4m in forbidden_234  # 4m
        assert 0 in forbidden_234  # 1m (suji tile)


_FIVE_PIN = tuple(tile_copies(copy, pin="5")[0] for copy in range(4))


def _round_after_seat_0_declared_four_kans(
    seat_2: MahjongPlayer,
    *,
    current_player_seat: int,
    seat_1_discards: tuple[Discard, ...] = (),
) -> MahjongRoundState:
    seat_0_kans = tuple(
        FrozenMeld(
            meld_type=FrozenMeld.KAN, tiles=tuple(tile_copies(0, man=str(number) * 4)), opened=False, who=0, from_who=0
        )
        for number in range(1, 5)
    )
    players = (
        create_player(seat=0, tiles=tile_copies(0, honors="7"), melds=seat_0_kans),
        create_player(
            seat=1,
            tiles=tile_copies(0, sou="123456789", honors="1234"),
            discards=seat_1_discards,
        ),
        seat_2,
        create_player(seat=3, tiles=tile_copies(1, sou="123456789", honors="1234")),
    )
    return create_dealt_game_state(players, current_player_seat=current_player_seat).round_state


class TestKanLimits:
    def test_can_call_open_kan__when_wall_below_min_for_kan__should_return_false(self):
        kan_caller = create_player(seat=1, tiles=(*_FIVE_PIN[1:], *tile_copies(0, man="123456789", honors="1")))
        players = (
            create_player(
                seat=0,
                tiles=tile_copies(0, sou="123456789", honors="2345"),
                discards=(Discard(tile_id=_FIVE_PIN[0]),),
            ),
            kan_caller,
            create_player(seat=2, tiles=tile_copies(1, sou="123456789", honors="1234")),
            create_player(seat=3, tiles=tile_copies(2, sou="123456789", honors="1234")),
        )
        runtime = GameRuntime(game_id="game", state=create_dealt_game_state(players), ai=AIPlayerController({}))
        settings = runtime.state.settings
        wall = runtime.state.round_state.wall
        short_live_tiles = wall.live_tiles[: settings.min_wall_for_kan - 1]
        round_state = _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": short_live_tiles}))

        assert (
            can_call_open_kan(kan_caller, discarded_tile=_FIVE_PIN[0], round_state=round_state, settings=settings)
            is False
        )

    def test_can_call_open_kan__when_four_kans_already_made__should_return_false(self):
        kan_caller = create_player(
            seat=2,
            tiles=(*_FIVE_PIN[1:], *tile_copies(0, pin="1234"), *tile_copies(2, sou="123456")),
        )
        round_state = _round_after_seat_0_declared_four_kans(
            kan_caller, current_player_seat=1, seat_1_discards=(Discard(tile_id=_FIVE_PIN[0]),)
        )

        assert (
            can_call_open_kan(kan_caller, discarded_tile=_FIVE_PIN[0], round_state=round_state, settings=GameSettings())
            is False
        )

    def test_get_possible_closed_kans__when_four_kans_already_made__should_return_empty(self):
        kan_caller = create_player(
            seat=2,
            tiles=(*_FIVE_PIN, *tile_copies(0, pin="12346789"), *tile_copies(2, sou="12")),
        )
        round_state = _round_after_seat_0_declared_four_kans(kan_caller, current_player_seat=2)

        assert get_possible_closed_kans(kan_caller, round_state, settings=GameSettings()) == []

    def test_get_possible_added_kans__when_four_kans_already_made__should_return_empty(self):
        five_pin_pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=_FIVE_PIN[:3],
            opened=True,
            called_tile=_FIVE_PIN[0],
            who=2,
            from_who=1,
        )
        kan_caller = create_player(
            seat=2,
            tiles=(_FIVE_PIN[3], *tile_copies(0, pin="12346789"), *tile_copies(2, sou="12")),
            melds=(five_pin_pon,),
        )
        round_state = _round_after_seat_0_declared_four_kans(
            kan_caller, current_player_seat=2, seat_1_discards=(Discard(tile_id=_FIVE_PIN[0]),)
        )

        assert get_possible_added_kans(kan_caller, round_state, settings=GameSettings()) == []


class TestChiKuikaeWithoutSuji:
    def test_chi_kuikae__when_suji_kuikae_disabled__should_forbid_only_called_tile(self):
        man_tiles = TilesConverter.string_to_136_array(man="123")
        pin_tiles = TilesConverter.string_to_136_array(pin="123456789")
        player1_tiles = (man_tiles[1], man_tiles[2], *pin_tiles)

        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            current_player_seat=0,
        )

        settings = GameSettings(has_kuikae=True, has_kuikae_suji=False)
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
    def test_validate_chi_sequence__when_honor_tiles__should_raise(self):
        honors = TilesConverter.string_to_136_array(honors="123")
        with pytest.raises(InvalidMeldError, match="honor tiles"):
            _validate_chi_sequence(honors[0], (honors[1], honors[2]))

    def test_validate_chi_sequence__when_mixed_suits__should_raise(self):
        man_1 = TilesConverter.string_to_136_array(man="1")[0]
        pin_2 = TilesConverter.string_to_136_array(pin="2")[0]
        sou_3 = TilesConverter.string_to_136_array(sou="3")[0]
        with pytest.raises(InvalidMeldError, match="same suit"):
            _validate_chi_sequence(man_1, (pin_2, sou_3))

    def test_validate_chi_sequence__when_not_consecutive__should_raise(self):
        man_tiles = TilesConverter.string_to_136_array(man="124")
        with pytest.raises(InvalidMeldError, match="consecutive sequence"):
            _validate_chi_sequence(man_tiles[0], (man_tiles[1], man_tiles[2]))


class TestCheckPaoDisabled:
    def test_pao__when_daisangen_pao_disabled__should_return_none(self):
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
        result = _check_pao(player, discarder_seat=2, called_tile_34=chun_34, settings=settings)
        assert result is None

    def test_pao__when_daisuushii_pao_disabled__should_return_none(self):
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
        result = _check_pao(player, discarder_seat=3, called_tile_34=north_34, settings=settings)
        assert result is None
