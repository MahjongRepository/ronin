import pytest
from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import ScoringContext, calculate_hand_value
from game.logic.settings import GameSettings, RenhouValue
from game.logic.state import Discard, MahjongPlayer
from game.logic.state_utils import update_player
from game.logic.win import can_call_ron, can_declare_tsumo, check_tsumo_with_tiles, is_renhou
from game.tests.conftest import create_dealt_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies


def _make_round_state(*, wall=None, dead_wall=None, dora_indicators=None):
    return create_round_state(
        wall=tuple(range(70)) if wall is None else wall,
        dead_wall=dead_wall,
        dora_indicators=TilesConverter.string_to_136_array(man="9") if dora_indicators is None else dora_indicators,
    )


class TestKuitanToggle:
    def test_kuitan__when_enabled_and_open_tanyao_tsumo__should_allow_declare(self):
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = _make_round_state()

        assert can_declare_tsumo(player, round_state, settings=GameSettings(has_kuitan=True)) is True

    def test_kuitan__when_disabled_and_open_tanyao_tsumo__should_reject_declare(self):
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = _make_round_state()

        assert can_declare_tsumo(player, round_state, settings=GameSettings(has_kuitan=False)) is False

    def test_kuitan__when_disabled_and_closed_tanyao__should_allow_declare(self):
        tiles = TilesConverter.string_to_136_array(man="234567", pin="234", sou="23455")
        player = MahjongPlayer(seat=0, name="P0", tiles=tuple(tiles), score=25000)
        round_state = _make_round_state()

        # menzen tsumo is a yaku by itself, so closed tanyao is allowed
        assert can_declare_tsumo(player, round_state, settings=GameSettings(has_kuitan=False)) is True

    @pytest.mark.parametrize(("has_kuitan", "can_ron"), [(True, True), (False, False)])
    def test_kuitan__when_open_tanyao_ron__should_follow_the_setting(self, has_kuitan, can_ron):
        eight_sou = tile_copies(0, sou="888")
        five_sou_ron = tile_copies(1, sou="5")[0]
        eight_sou_pon = FrozenMeld(
            meld_type=FrozenMeld.PON, tiles=tuple(eight_sou), opened=True, called_tile=eight_sou[0], who=1, from_who=0
        )
        players = (
            create_player(
                seat=0, tiles=tile_copies(1, man="123456789", honors="1234"), discards=(Discard(tile_id=eight_sou[0]),)
            ),
            create_player(
                seat=1,
                tiles=tile_copies(0, man="234567", pin="234", sou="5"),
                melds=(eight_sou_pon,),
                discards=(Discard(tile_id=tile_copies(1, honors="7")[0]),),
            ),
            create_player(
                seat=2,
                tiles=tile_copies(2, man="123456789", honors="1234"),
                discards=(Discard(tile_id=tile_copies(2, honors="7")[0]),),
            ),
            create_player(
                seat=3, tiles=tile_copies(3, man="123456789", honors="1234"), discards=(Discard(tile_id=five_sou_ron),)
            ),
        )
        round_state = create_dealt_game_state(players, current_player_seat=3).round_state
        tanyao_caller = round_state.players[1]
        assert check_tsumo_with_tiles(tanyao_caller, [*tanyao_caller.tiles, five_sou_ron]) is True

        settings = GameSettings(has_kuitan=has_kuitan)
        assert (
            can_call_ron(tanyao_caller, discarded_tile=five_sou_ron, round_state=round_state, settings=settings)
            is can_ron
        )


class TestIppatsuToggle:
    def test_ippatsu__when_setting_enabled__should_credit_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        discard_tile = TilesConverter.string_to_136_array(sou="9")[0]
        round_state = _make_round_state()
        # add all_discards to prevent tenhou detection
        round_state = round_state.model_copy(update={"all_discards": (discard_tile,)})
        round_state = update_player(
            round_state,
            0,
            tiles=tuple(tiles),
            is_riichi=True,
            is_ippatsu=True,
            discards=(Discard(tile_id=discard_tile),),
        )

        player = round_state.players[0]
        win_tile = tiles[-1]
        settings = GameSettings(has_ippatsu=True)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)

        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        # yaku_id 3 = ippatsu
        assert any(y.yaku_id == 3 for y in result.yaku)

    def test_ippatsu__when_setting_disabled__should_not_credit_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        discard_tile = TilesConverter.string_to_136_array(sou="9")[0]
        round_state = _make_round_state()
        round_state = round_state.model_copy(update={"all_discards": (discard_tile,)})
        round_state = update_player(
            round_state,
            0,
            tiles=tuple(tiles),
            is_riichi=True,
            is_ippatsu=True,
            discards=(Discard(tile_id=discard_tile),),
        )

        player = round_state.players[0]
        win_tile = tiles[-1]
        settings = GameSettings(has_ippatsu=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)

        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert not any(y.yaku_id == 3 for y in result.yaku)


class TestRenhouToggle:
    def _make_renhou_round_state(self):
        players = tuple(create_player(seat=i) for i in range(4))
        return create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            all_discards=(),
            wall=tuple(range(70)),
            dora_indicators=TilesConverter.string_to_136_array(man="9"),
        )

    def test_renhou_value__when_none__should_not_award_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="234", pin="234", sou="234678", honors="11")
        round_state = self._make_renhou_round_state()
        round_state = update_player(round_state, 1, tiles=tuple(tiles))

        player = round_state.players[1]
        win_tile = tiles[-1]
        settings = GameSettings(renhou_value=RenhouValue.NONE)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)

        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        # yaku_id 11 = renhou
        assert not any(y.yaku_id == 11 for y in result.yaku)

    def test_renhou_value__when_mangan__should_award_at_least_5_han(self):
        tiles = TilesConverter.string_to_136_array(man="234", pin="234", sou="234678", honors="11")
        round_state = self._make_renhou_round_state()
        round_state = update_player(round_state, 1, tiles=tuple(tiles))

        player = round_state.players[1]
        win_tile = tiles[-1]
        settings = GameSettings(renhou_value=RenhouValue.MANGAN)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)

        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert any(y.yaku_id == 11 for y in result.yaku)
        assert result.han >= 5


class TestRenhouEligibility:
    def test_renhou__when_dealer__should_not_be_eligible(self):
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
        )
        assert is_renhou(round_state.players[0], round_state) is False

    def test_renhou__when_non_dealer_before_any_discard__should_be_eligible(self):
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
        )
        assert is_renhou(round_state.players[1], round_state) is True

    def test_renhou__when_any_call_made__should_not_be_eligible(self):
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(pin="555")),
            opened=True,
            who=3,
            from_who=2,
        )
        players = (*(create_player(seat=i) for i in range(3)), create_player(seat=3, melds=(pon,)))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
        )
        assert is_renhou(round_state.players[1], round_state) is False

    def test_renhou__when_player_already_discarded__should_not_be_eligible(self):
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
        )
        tile = TilesConverter.string_to_136_array(man="1")[0]
        round_state = update_player(round_state, 1, discards=(Discard(tile_id=tile),))

        assert is_renhou(round_state.players[1], round_state) is False

    def test_renhou__when_tsumo__should_not_award_yaku(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        round_state = create_round_state(
            wall=tuple(range(70)),
            dora_indicators=TilesConverter.string_to_136_array(man="9"),
            all_discards=(),
        )
        round_state = update_player(round_state, 1, tiles=tuple(tiles))
        player = round_state.players[1]
        win_tile = tiles[-1]

        # tsumo context: renhou should not appear
        ctx_tsumo = ScoringContext(
            player=player,
            round_state=round_state,
            settings=GameSettings(),
            is_tsumo=True,
        )
        result_tsumo = calculate_hand_value(ctx_tsumo, win_tile)
        assert not any(y.yaku_id == 11 for y in result_tsumo.yaku)

    def test_renhou__when_closed_kan_made__should_not_be_eligible(self):
        players = tuple(create_player(seat=i) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            all_discards=(),
        )
        kan_tiles = TilesConverter.string_to_136_array(man="1111")
        closed_kan = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(kan_tiles), opened=False)
        round_state = update_player(round_state, 0, melds=(closed_kan,))

        assert is_renhou(round_state.players[1], round_state) is False
