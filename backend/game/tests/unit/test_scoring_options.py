from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import ScoringContext, calculate_hand_value
from game.logic.settings import GameSettings
from game.logic.state import Discard
from game.logic.state_utils import update_player
from game.tests.conftest import create_player, create_round_state


def _make_round_state(*, dealer_seat=0, round_wind=0, dora_indicators=None):
    dummy_discard = (Discard(tile_id=0),)
    players = tuple(create_player(seat=i, score=25000, discards=dummy_discard) for i in range(4))
    return create_round_state(
        players=players,
        dealer_seat=dealer_seat,
        current_player_seat=0,
        round_wind=round_wind,
        wall=tuple(range(70)),
        dead_wall=tuple(range(14)),
        dora_indicators=TilesConverter.string_to_136_array(man="9") if dora_indicators is None else dora_indicators,
        all_discards=TilesConverter.string_to_136_array(man="1112"),
    )


class TestDoubleWindPairFu:
    def test_calculate_hand_value__when_pair_is_double_wind__should_add_4_fu(self):
        # Seat 0, dealer_seat=0 -> player wind = East (27)
        # round_wind=0 -> round wind = East (27)
        # Hand: 123m 456m 789p EE + 23s waiting for 4s (ryanmen)
        closed = TilesConverter.string_to_136_array(man="123456", pin="789", sou="23")
        east_pair = TilesConverter.string_to_136_array(honors="11")
        all_tiles = (*tuple(closed), *tuple(east_pair))

        round_state = _make_round_state(dealer_seat=0, round_wind=0)
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        final_tiles = (*all_tiles, win_tile)

        round_state = update_player(round_state, 0, tiles=final_tiles)
        player = round_state.players[0]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # Base 20 (tsumo) + 4 (double valued pair) + 2 (tsumo fu) = 26, rounds to 30
        assert result.fu == 30

    def test_calculate_hand_value__when_pair_is_single_wind__should_add_2_fu(self):
        # Seat 0, dealer_seat=0 -> player wind = East
        # round_wind=1 -> round wind = South
        # East pair = single valued pair (player wind only) = 2 fu
        closed = TilesConverter.string_to_136_array(man="123456", pin="789", sou="23")
        east_pair = TilesConverter.string_to_136_array(honors="11")
        all_tiles = (*tuple(closed), *tuple(east_pair))

        round_state = _make_round_state(dealer_seat=0, round_wind=1)
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        final_tiles = (*all_tiles, win_tile)

        round_state = update_player(round_state, 0, tiles=final_tiles)
        player = round_state.players[0]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # Base 20 (tsumo) + 2 (single valued pair) + 2 (tsumo fu) = 24, rounds to 30
        assert result.fu == 30

    def test_calculate_hand_value__when_ron_with_double_vs_single_wind_pair__should_give_double_more_fu(self):
        # Hand: 111m (closed terminal pon = 8 fu) + 456m + 789p + EE pair + 23s wait on 4s
        # Closed ron: base 30 + 8 (terminal pon) + pair fu + 0 (ryanmen) = 38 or 42
        # Single pair: 30 + 8 + 2 = 40 fu (exactly 40, no rounding)
        # Double pair: 30 + 8 + 4 = 42 fu -> rounds to 50 fu
        closed = TilesConverter.string_to_136_array(man="111456", pin="789", sou="23")
        east_pair = TilesConverter.string_to_136_array(honors="11")
        all_tiles = (*tuple(closed), *tuple(east_pair))
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        final_tiles = (*all_tiles, win_tile)
        settings = GameSettings(has_akadora=False)

        # Double wind ron: East round, East player -> 4 fu pair -> 50 fu total
        no_dora = TilesConverter.string_to_136_array(pin="9")
        rs_double = _make_round_state(dealer_seat=0, round_wind=0, dora_indicators=no_dora)
        rs_double = update_player(rs_double, 0, tiles=final_tiles, is_riichi=True)
        ctx_double = ScoringContext(
            player=rs_double.players[0],
            round_state=rs_double,
            settings=settings,
            is_tsumo=False,
        )
        result_double = calculate_hand_value(ctx_double, win_tile)

        # Single wind ron: South round, East player -> 2 fu pair -> 40 fu total
        rs_single = _make_round_state(dealer_seat=0, round_wind=1, dora_indicators=no_dora)
        rs_single = update_player(rs_single, 0, tiles=final_tiles, is_riichi=True)
        ctx_single = ScoringContext(
            player=rs_single.players[0],
            round_state=rs_single,
            settings=settings,
            is_tsumo=False,
        )
        result_single = calculate_hand_value(ctx_single, win_tile)

        assert result_double.error is None
        assert result_single.error is None
        assert result_double.fu > result_single.fu

    def test_calculate_hand_value__when_pair_not_valued__should_add_no_pair_fu(self):
        # Pinfu hand: 123m 456m 789p 55s (non-valued pair) + 23s wait on 4s (ryanmen)
        tiles = TilesConverter.string_to_136_array(man="123456", pin="789", sou="2355")
        round_state = _make_round_state(dealer_seat=0, round_wind=0)
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        final_tiles = (*tuple(tiles), win_tile)

        round_state = update_player(round_state, 1, tiles=final_tiles)
        player = round_state.players[1]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # Pinfu tsumo: base 20, no set fu, no pair fu, no tsumo fu = 20 fu
        assert result.fu == 20


class TestChiitoitsuFu:
    def test_calculate_hand_value__when_chiitoitsu__should_score_25_fu(self):
        tiles = TilesConverter.string_to_136_array(man="1133", pin="2277", sou="5588", honors="11")
        round_state = _make_round_state()
        win_tile = tiles[-1]
        round_state = update_player(round_state, 0, tiles=tuple(tiles))
        player = round_state.players[0]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.fu == 25

    def test_calculate_hand_value__when_chiitoitsu__should_give_yaku_worth_2_han(self):
        tiles = TilesConverter.string_to_136_array(man="1133", pin="2277", sou="5588", honors="11")
        round_state = _make_round_state()
        win_tile = tiles[-1]
        round_state = update_player(round_state, 0, tiles=tuple(tiles))
        player = round_state.players[0]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # Chiitoitsu (2 han) + menzen tsumo (1 han) = 3 han minimum
        assert result.han >= 3
        # Verify chiitoitsu yaku (yaku_id=34) is present with 2 han
        chiitoitsu_yaku = [y for y in result.yaku if y.yaku_id == 34]
        assert len(chiitoitsu_yaku) == 1
        assert chiitoitsu_yaku[0].han == 2


class TestPinfuTsumoFu:
    def _make_pinfu_tiles(self):
        closed = TilesConverter.string_to_136_array(man="123456", pin="789", sou="2355")
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        return closed, win_tile

    def test_calculate_hand_value__when_pinfu_tsumo_fu_disabled__should_score_20_fu(self):
        closed, win_tile = self._make_pinfu_tiles()
        final_tiles = (*tuple(closed), win_tile)

        round_state = _make_round_state()
        round_state = update_player(round_state, 1, tiles=final_tiles)
        player = round_state.players[1]

        settings = GameSettings(fu_for_pinfu_tsumo=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.fu == 20

    def test_calculate_hand_value__when_pinfu_tsumo_fu_enabled__should_add_tsumo_fu(self):
        closed, win_tile = self._make_pinfu_tiles()
        final_tiles = (*tuple(closed), win_tile)

        round_state = _make_round_state()
        round_state = update_player(round_state, 1, tiles=final_tiles)
        player = round_state.players[1]

        settings = GameSettings(fu_for_pinfu_tsumo=True)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # base 20 + 2 tsumo fu = 22, rounds up to 30
        assert result.fu == 30


class TestOpenPinfuFu:
    def _make_open_pinfu_state(self, *, fu_for_open_pinfu: bool):
        closed_tiles = TilesConverter.string_to_136_array(man="567", pin="23455", sou="23")
        chi_tiles = TilesConverter.string_to_136_array(man="234")
        chi = FrozenMeld(
            meld_type=FrozenMeld.CHI,
            tiles=tuple(chi_tiles),
            opened=True,
            called_tile=chi_tiles[0],
            who=0,
            from_who=3,
        )

        round_state = _make_round_state()
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        final_tiles = (*tuple(closed_tiles), win_tile)

        round_state = update_player(round_state, 0, tiles=final_tiles, melds=(chi,))
        player = round_state.players[0]

        settings = GameSettings(fu_for_open_pinfu=fu_for_open_pinfu, has_kuitan=True)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        return ctx, win_tile

    def test_calculate_hand_value__when_open_pinfu_fu_enabled__should_add_2_fu(self):
        ctx, win_tile = self._make_open_pinfu_state(fu_for_open_pinfu=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # Open hand ron: base 20 + 2 fu (open pinfu) = 22, rounds to 30
        assert result.fu == 30

    def test_calculate_hand_value__when_open_pinfu_fu_disabled__should_score_20_fu(self):
        ctx, win_tile = self._make_open_pinfu_state(fu_for_open_pinfu=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # Open hand ron: base 20 + 0 fu = 20
        assert result.fu == 20


class TestKiriageMangan:
    def test_calculate_hand_value__when_kiriage_enabled_and_4_han_30_fu__should_score_mangan(self):
        # tanyao (1) + pinfu (1) + iipeiko (1) + riichi (1) = 4 han, pinfu ron = 30 fu
        tiles = TilesConverter.string_to_136_array(man="223344", pin="567", sou="234")
        pair_tile = TilesConverter.string_to_136_array(man="55")
        all_tiles = (*tuple(tiles), pair_tile[0])

        round_state = _make_round_state(dora_indicators=TilesConverter.string_to_136_array(pin="9"))
        win_tile = pair_tile[1]
        final_tiles = (*all_tiles, win_tile)

        round_state = update_player(round_state, 1, tiles=final_tiles, is_riichi=True)
        player = round_state.players[1]

        settings = GameSettings(has_kiriage_mangan=True, has_akadora=False, has_uradora=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han == 4
        assert result.fu == 30
        # Kiriage: 4/30 -> mangan (8000 for non-dealer ron)
        assert result.cost_main == 8000

    def test_calculate_hand_value__when_kiriage_disabled_and_4_han_30_fu__should_score_7700(self):
        tiles = TilesConverter.string_to_136_array(man="223344", pin="567", sou="234")
        pair_tile = TilesConverter.string_to_136_array(man="55")
        all_tiles = (*tuple(tiles), pair_tile[0])

        round_state = _make_round_state(dora_indicators=TilesConverter.string_to_136_array(pin="9"))
        win_tile = pair_tile[1]
        final_tiles = (*all_tiles, win_tile)

        round_state = update_player(round_state, 1, tiles=final_tiles, is_riichi=True)
        player = round_state.players[1]

        settings = GameSettings(has_kiriage_mangan=False, has_akadora=False, has_uradora=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han == 4
        assert result.fu == 30
        # Without kiriage: 30 * 2^6 = 1920 base -> 7700 non-dealer ron
        assert result.cost_main == 7700
