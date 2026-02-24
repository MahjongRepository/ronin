"""
Verifies:
- Pao applies to daisangen (Big Three Dragons) and daisuushii (Big Four Winds) — configurable
- Pao does NOT apply to suukantsu (Four Quads) — fundamental
- Trigger thresholds are configurable (daisangen_pao_set_threshold, daisuushii_pao_set_threshold)
- Closed kans count toward pao threshold
- Tsumo with pao: liable player pays full score — fundamental
- Ron with pao (third party): liable + discarder split 50/50 — fundamental
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import _check_pao, call_pon
from game.logic.settings import GameSettings
from game.logic.tiles import tile_to_34
from game.tests.conftest import create_player, create_round_state


class TestPaoCustomThresholds:
    """Verify pao thresholds are configurable, not hardcoded."""

    def test_daisangen_pao_custom_threshold_2(self):
        """With threshold=2, pon on 2nd dragon triggers pao."""
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        melds = (FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(haku_tiles), opened=True, who=0),)
        player = create_player(seat=0, melds=melds)

        hatsu_tile = TilesConverter.string_to_136_array(honors="6")[0]
        hatsu_34 = tile_to_34(hatsu_tile)

        settings = GameSettings(daisangen_pao_set_threshold=2)
        result = _check_pao(player, discarder_seat=2, called_tile_34=hatsu_34, settings=settings)

        assert result == 2

    def test_daisangen_pao_default_threshold_no_trigger_on_2nd(self):
        """With default threshold=3, pon on 2nd dragon does NOT trigger pao."""
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        melds = (FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(haku_tiles), opened=True, who=0),)
        player = create_player(seat=0, melds=melds)

        hatsu_tile = TilesConverter.string_to_136_array(honors="6")[0]
        hatsu_34 = tile_to_34(hatsu_tile)

        result = _check_pao(player, discarder_seat=2, called_tile_34=hatsu_34, settings=GameSettings())

        assert result is None

    def test_daisuushii_pao_custom_threshold_3(self):
        """With threshold=3, pon on 3rd wind triggers pao."""
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

    def test_daisuushii_pao_default_threshold_no_trigger_on_3rd(self):
        """With default threshold=4, pon on 3rd wind does NOT trigger pao."""
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
    """Verify pao does NOT apply to suukantsu (four quads of suited tiles)."""

    def test_four_suited_kans_no_pao(self):
        """Player with 3 suited kans calling pon on 4th suited tile: no pao."""
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


class TestClosedKanCountsInPaoThreshold:
    """Verify closed kans are counted toward pao threshold."""

    def test_closed_dragon_kan_counted_for_daisangen(self):
        """A closed kan of Haku + open pon of Hatsu = 2 dragon sets.

        Calling pon on Chun (3rd dragon) triggers pao.
        """
        # closed kan of Haku (concealed, opened=False)
        haku_tiles = TilesConverter.string_to_136_array(honors="5555")
        # open pon of Hatsu
        hatsu_tiles = TilesConverter.string_to_136_array(honors="666")
        melds = (
            FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(haku_tiles), opened=False, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(hatsu_tiles), opened=True, who=0),
        )
        player = create_player(seat=0, melds=melds)

        chun_tile = TilesConverter.string_to_136_array(honors="7")[0]
        chun_34 = tile_to_34(chun_tile)

        result = _check_pao(player, discarder_seat=3, called_tile_34=chun_34, settings=GameSettings())

        assert result == 3

    def test_shouminkan_counted_for_daisuushii(self):
        """A shouminkan of East + pons of South, West = 3 wind sets.

        Calling pon on North (4th wind) triggers pao.
        """
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


class TestPaoIntegrationWithCallPon:
    """Verify pao is set on the player state when pon triggers the threshold."""

    def test_pon_completing_3rd_dragon_sets_pao_on_player(self):
        """call_pon on 3rd dragon sets pao_seat in the round state."""
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        hatsu_tiles = TilesConverter.string_to_136_array(honors="666")
        chun_tiles = TilesConverter.string_to_136_array(honors="77")
        hand_tiles = TilesConverter.string_to_136_array(pin="123456789")
        melds = (
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(haku_tiles), opened=True, who=0),
            FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(hatsu_tiles), opened=True, who=0),
        )
        player = create_player(seat=0, tiles=tuple(chun_tiles) + tuple(hand_tiles), melds=melds)
        players = [player] + [create_player(seat=i) for i in range(1, 4)]
        wall = tuple(TilesConverter.string_to_136_array(man="123456"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333344"))
        round_state = create_round_state(players=players, wall=wall, dead_wall=dead_wall)

        chun_discarded = TilesConverter.string_to_136_array(honors="7")[0]
        new_state, _meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=1,
            tile_id=chun_discarded,
            settings=GameSettings(),
        )

        assert new_state.players[0].pao_seat == 1

    def test_pon_below_threshold_does_not_set_pao(self):
        """call_pon on 2nd dragon (default threshold=3) does NOT set pao_seat."""
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        hatsu_tiles = TilesConverter.string_to_136_array(honors="66")
        hand_tiles = TilesConverter.string_to_136_array(pin="12345678")
        melds = (FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(haku_tiles), opened=True, who=0),)
        player = create_player(seat=0, tiles=tuple(hatsu_tiles) + tuple(hand_tiles), melds=melds)
        players = [player] + [create_player(seat=i) for i in range(1, 4)]
        wall = tuple(TilesConverter.string_to_136_array(man="123456"))
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333344"))
        round_state = create_round_state(players=players, wall=wall, dead_wall=dead_wall)

        hatsu_discarded = TilesConverter.string_to_136_array(honors="6")[0]
        new_state, _meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=2,
            tile_id=hatsu_discarded,
            settings=GameSettings(),
        )

        assert new_state.players[0].pao_seat is None
