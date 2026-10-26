import pytest
from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_discard, handle_kan, handle_pon
from game.logic.action_result import ActionResult
from game.logic.enums import KanType
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import _check_pao
from game.logic.settings import GameSettings
from game.logic.state import Discard
from game.logic.tiles import tile_to_34
from game.logic.types import DiscardActionData, KanActionData, PonActionData
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import tile_copies


class TestPaoCustomThresholds:
    def test_pao__when_daisangen_threshold_is_2_and_second_dragon_called__should_assign_pao(self):
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        melds = (FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(haku_tiles), opened=True, who=0),)
        player = create_player(seat=0, melds=melds)

        hatsu_tile = TilesConverter.string_to_136_array(honors="6")[0]
        hatsu_34 = tile_to_34(hatsu_tile)

        settings = GameSettings(daisangen_pao_set_threshold=2)
        result = _check_pao(player, discarder_seat=2, called_tile_34=hatsu_34, settings=settings)
        assert result == 2

    def test_pao__when_second_dragon_called_with_default_threshold__should_not_assign_pao(self):
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        melds = (FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(haku_tiles), opened=True, who=0),)
        player = create_player(seat=0, melds=melds)

        hatsu_tile = TilesConverter.string_to_136_array(honors="6")[0]
        hatsu_34 = tile_to_34(hatsu_tile)

        result = _check_pao(player, discarder_seat=2, called_tile_34=hatsu_34, settings=GameSettings())
        assert result is None

    def test_pao__when_daisuushii_threshold_is_3_and_third_wind_called__should_assign_pao(self):
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        south_tiles = TilesConverter.string_to_136_array(honors="222")
        melds = (
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(east_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(south_tiles), opened=True, who=0),
        )
        player = create_player(seat=0, melds=melds)

        west_tile = TilesConverter.string_to_136_array(honors="3")[0]
        west_34 = tile_to_34(west_tile)

        settings = GameSettings(daisuushii_pao_set_threshold=3)
        result = _check_pao(player, discarder_seat=1, called_tile_34=west_34, settings=settings)
        assert result == 1

    def test_pao__when_third_wind_called_with_default_threshold__should_not_assign_pao(self):
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        south_tiles = TilesConverter.string_to_136_array(honors="222")
        melds = (
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(east_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(south_tiles), opened=True, who=0),
        )
        player = create_player(seat=0, melds=melds)

        west_tile = TilesConverter.string_to_136_array(honors="3")[0]
        west_34 = tile_to_34(west_tile)

        result = _check_pao(player, discarder_seat=1, called_tile_34=west_34, settings=GameSettings())
        assert result is None


class TestNoSuukantsuPao:
    def test_pao__when_fourth_suited_kan_called__should_not_assign_pao(self):
        man1_tiles = TilesConverter.string_to_136_array(man="1111")
        man2_tiles = TilesConverter.string_to_136_array(man="2222")
        man3_tiles = TilesConverter.string_to_136_array(man="3333")
        melds = (
            FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(man1_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(man2_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(man3_tiles), opened=True, who=0),
        )
        player = create_player(seat=0, melds=melds)

        man4_tile = TilesConverter.string_to_136_array(man="4")[0]
        man4_34 = tile_to_34(man4_tile)

        result = _check_pao(player, discarder_seat=1, called_tile_34=man4_34, settings=GameSettings())
        assert result is None


class TestKanCountsInPaoThreshold:
    @pytest.mark.parametrize("is_open_kan", [False, True])
    def test_pao__when_dragon_kan_and_third_dragon_called__should_count_kan_and_assign_pao(self, is_open_kan):
        haku_tiles = TilesConverter.string_to_136_array(honors="5555")
        hatsu_tiles = TilesConverter.string_to_136_array(honors="666")
        melds = (
            FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(haku_tiles), opened=is_open_kan, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(hatsu_tiles), opened=True, who=0),
        )
        player = create_player(seat=0, melds=melds)

        chun_tile = TilesConverter.string_to_136_array(honors="7")[0]
        chun_34 = tile_to_34(chun_tile)

        result = _check_pao(player, discarder_seat=3, called_tile_34=chun_34, settings=GameSettings())
        assert result == 3

    def test_pao__when_shouminkan_and_fourth_wind_called__should_count_kan_and_assign_pao(self):
        east_tiles = TilesConverter.string_to_136_array(honors="1111")
        south_tiles = TilesConverter.string_to_136_array(honors="222")
        west_tiles = TilesConverter.string_to_136_array(honors="333")
        melds = (
            FrozenMeld(meld_type=FrozenMeld.SHOUMINKAN, tiles=tuple(east_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(south_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(west_tiles), opened=True, who=0),
        )
        player = create_player(seat=0, melds=melds)

        north_tile = TilesConverter.string_to_136_array(honors="4")[0]
        north_34 = tile_to_34(north_tile)

        result = _check_pao(player, discarder_seat=2, called_tile_34=north_34, settings=GameSettings())
        assert result == 2


_DRAGON_PON_DISCARDERS = {5: 2, 6: 3}


def _dragon_pons(honors: str) -> tuple[FrozenMeld, ...]:
    pons = []
    for honor in honors:
        pon_tiles = tile_copies(0, honors=honor * 3)
        pons.append(
            FrozenMeld(
                meld_type=FrozenMeld.PON,
                tiles=tuple(pon_tiles),
                opened=True,
                called_tile=pon_tiles[0],
                who=0,
                from_who=_DRAGON_PON_DISCARDERS[int(honor)],
            )
        )

    return tuple(pons)


def _discard_to_dragon_caller(*, dragon_pons: str, closed_tiles: tuple[int, ...], discarded: int) -> ActionResult:
    melds = _dragon_pons(dragon_pons)
    players = (
        create_player(
            seat=0,
            tiles=closed_tiles,
            melds=melds,
            discards=tuple(Discard(tile_id=t) for t in tile_copies(0, sou="12")[: len(melds)]),
        ),
        create_player(seat=1, tiles=(discarded, *tile_copies(1, sou="123456789", pin="1234"))),
        *(
            create_player(
                seat=seat,
                tiles=tile_copies(seat, sou="123456789", pin="1234"),
                discards=tuple(Discard(tile_id=m.called_tile) for m in melds if m.from_who == seat),
            )
            for seat in (2, 3)
        ),
    )
    game_state = create_dealt_game_state(players, current_player_seat=1)

    discard = handle_discard(game_state, seat=1, data=DiscardActionData(tile_id=discarded))
    assert isinstance(discard, ActionResult)
    prompt = discard.state.round_state.pending_call_prompt
    assert prompt is not None
    assert [c.seat for c in prompt.callers] == [0]
    return discard


class TestPaoOnCalls:
    def test_pao__when_pon_completes_third_dragon__should_make_discarder_liable(self):
        chun = tile_copies(0, honors="777")
        offered = _discard_to_dragon_caller(
            dragon_pons="56", closed_tiles=(*chun[:2], *tile_copies(0, man="12345")), discarded=chun[2]
        )

        pon = handle_pon(offered.state, seat=0, data=PonActionData(tile_id=chun[2]))
        assert isinstance(pon, ActionResult)
        assert pon.state.round_state.players[0].pao_seat == 1

    def test_pao__when_open_kan_completes_third_dragon__should_make_discarder_liable(self):
        chun = tile_copies(0, honors="7777")
        offered = _discard_to_dragon_caller(
            dragon_pons="56", closed_tiles=(*chun[:3], *tile_copies(0, man="1234")), discarded=chun[3]
        )

        kan = handle_kan(offered.state, seat=0, data=KanActionData(tile_id=chun[3], kan_type=KanType.OPEN))
        assert isinstance(kan, ActionResult)
        assert kan.state.round_state.players[0].melds[-1].type == FrozenMeld.KAN
        assert kan.state.round_state.players[0].pao_seat == 1

    def test_pao__when_two_dragon_pons_and_a_suited_pon__should_not_set_pao(self):
        nine_man = tile_copies(0, man="999")
        offered = _discard_to_dragon_caller(
            dragon_pons="56", closed_tiles=(*nine_man[:2], *tile_copies(0, man="12345")), discarded=nine_man[2]
        )

        pon = handle_pon(offered.state, seat=0, data=PonActionData(tile_id=nine_man[2]))
        assert isinstance(pon, ActionResult)
        assert pon.state.round_state.players[0].pao_seat is None

    @pytest.mark.parametrize(
        ("dragon_pons", "filler"),
        [("", tile_copies(0, man="123456789", pin="12")), ("5", tile_copies(0, man="12345678"))],
    )
    def test_pao__when_pon_is_below_threshold__should_not_set_pao(self, dragon_pons, filler):
        hatsu = tile_copies(0, honors="666")
        offered = _discard_to_dragon_caller(
            dragon_pons=dragon_pons, closed_tiles=(*hatsu[:2], *filler), discarded=hatsu[2]
        )

        pon = handle_pon(offered.state, seat=0, data=PonActionData(tile_id=hatsu[2]))
        assert isinstance(pon, ActionResult)
        assert pon.state.round_state.players[0].pao_seat is None
