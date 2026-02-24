"""
Verify that double wind pair fu, chiitoitsu fu/han, pinfu tsumo fu,
open pinfu fu, and kiriage mangan settings are properly handled
in the scoring pipeline.
"""

from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import ScoringContext, calculate_hand_value
from game.logic.settings import GameSettings, build_optional_rules
from game.logic.state import Discard
from game.logic.state_utils import update_player
from game.tests.conftest import create_player, create_round_state


def _make_round_state(*, dealer_seat=0, round_wind=0, dora_indicators=None):
    """Create a round state for scoring tests with mid-game state to avoid tenhou/chiihou."""
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
    """Verify double wind pair gives 4 fu when player wind equals round wind."""

    def test_double_wind_pair_gives_4_fu(self):
        """East player in East round with East pair gets 4 fu from the pair."""
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

    def test_single_wind_pair_gives_2_fu(self):
        """Player wind pair (not matching round wind) gives only 2 fu."""
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

    def test_double_wind_pair_produces_higher_fu_than_single_on_ron(self):
        """Double wind pair (4 fu) crosses a rounding boundary that single (2 fu) does not on ron."""
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

    def test_non_valued_pair_gives_no_pair_fu(self):
        """Non-valued pair (simple tile) gives 0 fu for the pair, producing pinfu 20 fu."""
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
    """Verify chiitoitsu always scores fixed 25 fu, 2 han."""

    def test_chiitoitsu_fixed_25_fu(self):
        """Chiitoitsu hand has exactly 25 fu."""
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

    def test_chiitoitsu_is_2_han(self):
        """Chiitoitsu yaku contributes exactly 2 han (closed hand)."""
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

    def test_chiitoitsu_25_fu_not_rounded_to_30(self):
        """Chiitoitsu 25 fu is preserved (not rounded up to 30 like other hands)."""
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


class TestPinfuTsumoFu:
    """Verify fu_for_pinfu_tsumo setting controls pinfu tsumo fu."""

    def _make_pinfu_tiles(self):
        """Return 13 closed tiles + a ryanmen win tile for a pinfu hand.

        Hand: 123m 456m 789p 55s pair, waiting on 23s -> 4s ryanmen.
        """
        closed = TilesConverter.string_to_136_array(man="123456", pin="789", sou="2355")
        win_tile = TilesConverter.string_to_136_array(sou="4")[0]
        return closed, win_tile

    def test_pinfu_tsumo_0_fu_when_disabled(self):
        """Pinfu tsumo scores 20 fu (no extra tsumo fu) when fu_for_pinfu_tsumo=False."""
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

    def test_pinfu_tsumo_with_fu_when_enabled(self):
        """Pinfu tsumo scores 30 fu (2 extra tsumo fu) when fu_for_pinfu_tsumo=True."""
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

    def test_fu_for_pinfu_tsumo_wired_through_optional_rules(self):
        """fu_for_pinfu_tsumo maps to the mahjong library's OptionalRules."""
        rules_disabled = build_optional_rules(GameSettings(fu_for_pinfu_tsumo=False))
        assert rules_disabled.fu_for_pinfu_tsumo is False
        rules_enabled = build_optional_rules(GameSettings(fu_for_pinfu_tsumo=True))
        assert rules_enabled.fu_for_pinfu_tsumo is True


class TestOpenPinfuFu:
    """Verify fu_for_open_pinfu setting controls open pinfu fu."""

    def _make_open_pinfu_state(self, *, fu_for_open_pinfu: bool):
        """Create an open tanyao hand with all sequences (0 fu from sets).

        Hand: 234m chi (open) + 567m 234p 55p pair + 23s waiting on 4s (ryanmen).
        Open tanyao provides yaku for ron.
        """
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

    def test_open_pinfu_2_fu_when_enabled(self):
        """Open pinfu hand gets 2 fu added when fu_for_open_pinfu=True, rounding to 30."""
        ctx, win_tile = self._make_open_pinfu_state(fu_for_open_pinfu=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # Open hand ron: base 20 + 2 fu (open pinfu) = 22, rounds to 30
        assert result.fu == 30

    def test_open_pinfu_no_fu_when_disabled(self):
        """Open pinfu hand gets no added fu when fu_for_open_pinfu=False, staying at 20."""
        ctx, win_tile = self._make_open_pinfu_state(fu_for_open_pinfu=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # Open hand ron: base 20 + 0 fu = 20
        assert result.fu == 20

    def test_fu_for_open_pinfu_wired_through_optional_rules(self):
        """fu_for_open_pinfu maps to the mahjong library's OptionalRules."""
        rules_enabled = build_optional_rules(GameSettings(fu_for_open_pinfu=True))
        assert rules_enabled.fu_for_open_pinfu is True
        rules_disabled = build_optional_rules(GameSettings(fu_for_open_pinfu=False))
        assert rules_disabled.fu_for_open_pinfu is False


class TestKiriageMangan:
    """Verify has_kiriage_mangan setting controls kiriage mangan scoring."""

    def test_kiriage_wired_through_optional_rules(self):
        """has_kiriage_mangan maps to kiriage in the mahjong library's OptionalRules."""
        rules_enabled = build_optional_rules(GameSettings(has_kiriage_mangan=True))
        assert rules_enabled.kiriage is True
        rules_disabled = build_optional_rules(GameSettings(has_kiriage_mangan=False))
        assert rules_disabled.kiriage is False

    def test_4_han_30_fu_scores_mangan_when_enabled(self):
        """4 han / 30 fu hand scores as mangan (8000 non-dealer ron) when kiriage is enabled."""
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

    def test_4_han_30_fu_scores_exact_when_disabled(self):
        """4 han / 30 fu hand scores 7700 (non-dealer ron) when kiriage is disabled."""
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
