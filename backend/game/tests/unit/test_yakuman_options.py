"""
Verify that double yakuman, yakuman stacking, kazoe yakuman,
yakuman-dora interaction, and sextuple yakuman cap settings
are properly configurable and correctly wired into scoring logic.
"""

from mahjong.hand_calculating.hand_config import HandConfig
from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import ScoringContext, calculate_hand_value
from game.logic.settings import GameSettings, build_optional_rules
from game.logic.state import Discard
from game.logic.state_utils import update_player
from game.tests.conftest import create_game_state, create_player, create_round_state


def _make_scoring_game_state(
    *,
    dealer_seat: int = 0,
    dora_indicators=None,
    settings: GameSettings | None = None,
):
    """Create a game state for scoring tests with mid-game state to avoid tenhou/chiihou."""
    dummy_discard = (Discard(tile_id=0),)
    players = tuple(create_player(seat=i, score=25000, discards=dummy_discard) for i in range(4))
    if dora_indicators is None:
        dora_indicators = TilesConverter.string_to_136_array(man="1")
    round_state = create_round_state(
        players=players,
        dealer_seat=dealer_seat,
        current_player_seat=0,
        round_wind=0,
        dora_indicators=dora_indicators,
        wall=tuple(range(70)),
        dead_wall=tuple(range(14)),
        all_discards=TilesConverter.string_to_136_array(man="1112"),
    )
    return create_game_state(round_state=round_state, settings=settings)


class TestDoubleYakumanSetting:
    """Verify has_double_yakuman setting controls double yakuman scoring."""

    def test_double_yakuman_enabled_scores_26_han(self):
        """Suuankou tanki scores 26 han when has_double_yakuman=True."""
        tiles = TilesConverter.string_to_136_array(man="111", pin="333", sou="555777")
        pair_tiles = TilesConverter.string_to_136_array(sou="99")
        all_tiles = (*tuple(tiles), pair_tiles[0])

        game_state = _make_scoring_game_state()
        win_tile = pair_tiles[1]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles)
        player = round_state.players[1]

        settings = GameSettings(has_double_yakuman=True)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han == 26

    def test_double_yakuman_disabled_scores_13_han(self):
        """Suuankou tanki scores 13 han (single yakuman) when has_double_yakuman=False."""
        tiles = TilesConverter.string_to_136_array(man="111", pin="333", sou="555777")
        pair_tiles = TilesConverter.string_to_136_array(sou="99")
        all_tiles = (*tuple(tiles), pair_tiles[0])

        game_state = _make_scoring_game_state()
        win_tile = pair_tiles[1]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles)
        player = round_state.players[1]

        settings = GameSettings(has_double_yakuman=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han == 13
        # single yakuman non-dealer tsumo: dealer pays 16000, non-dealer pays 8000
        assert result.cost_main == 16000
        assert result.cost_additional == 8000

    def test_daisuushii_disabled_scores_13_han(self):
        """Daisuushii alone scores 13 han (single yakuman) when has_double_yakuman=False."""
        # pair is 1m (not honor), so tsuuiisou does NOT apply — only daisuushii
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        closed_tiles = TilesConverter.string_to_136_array(honors="222333444")
        man_pair = TilesConverter.string_to_136_array(man="11")
        all_tiles = tuple(east_tiles) + tuple(closed_tiles) + (man_pair[0],)

        east_pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(east_tiles),
            opened=True,
            called_tile=east_tiles[0],
            who=1,
            from_who=0,
        )

        game_state = _make_scoring_game_state()
        win_tile = man_pair[1]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles, melds=(east_pon,))
        player = round_state.players[1]

        settings = GameSettings(has_double_yakuman=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # daisuushii downgraded to 13 han (single yakuman), no tsuuiisou (pair is man, not honor)
        assert result.han == 13
        # single yakuman non-dealer ron: 32000
        assert result.cost_main == 32000

    def test_setting_wired_to_optional_rules(self):
        """has_double_yakuman maps to the mahjong library's OptionalRules."""
        rules_enabled = build_optional_rules(GameSettings(has_double_yakuman=True))
        assert rules_enabled.has_double_yakuman is True

        rules_disabled = build_optional_rules(GameSettings(has_double_yakuman=False))
        assert rules_disabled.has_double_yakuman is False


class TestYakumanStacking:
    """Verify that multiple yakuman hands in the same hand stack correctly."""

    def test_daisuushii_plus_tsuuiisou_stacks(self):
        """Daisuushii + Tsuuiisou in the same hand stack their yakuman values."""
        # Open daisuushii + tsuuiisou: EEE(open) SSS WWW NNN + Haku pair
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        closed_tiles = TilesConverter.string_to_136_array(honors="222333444")
        pair_tiles = TilesConverter.string_to_136_array(honors="55")
        all_tiles = tuple(east_tiles) + tuple(closed_tiles) + (pair_tiles[0],)

        east_pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(east_tiles),
            opened=True,
            called_tile=east_tiles[0],
            who=1,
            from_who=0,
        )

        game_state = _make_scoring_game_state()
        win_tile = pair_tiles[1]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles, melds=(east_pon,))
        player = round_state.players[1]

        settings = GameSettings(has_double_yakuman=True)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # daisuushii (26 han, double yakuman) + tsuuiisou (13 han, yakuman) = 39 han
        assert result.han == 39

    def test_stacking_with_double_yakuman_disabled(self):
        """Stacking still works but individual values are reduced when double yakuman is off."""
        # Same hand: daisuushii + tsuuiisou, but with double yakuman disabled
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        closed_tiles = TilesConverter.string_to_136_array(honors="222333444")
        pair_tiles = TilesConverter.string_to_136_array(honors="55")
        all_tiles = tuple(east_tiles) + tuple(closed_tiles) + (pair_tiles[0],)

        east_pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(east_tiles),
            opened=True,
            called_tile=east_tiles[0],
            who=1,
            from_who=0,
        )

        game_state = _make_scoring_game_state()
        win_tile = pair_tiles[1]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles, melds=(east_pon,))
        player = round_state.players[1]

        settings = GameSettings(has_double_yakuman=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # daisuushii (13 han, downgraded) + tsuuiisou (13 han) = 26 han (double yakuman)
        assert result.han == 26

    def test_stacking_produces_correct_payment(self):
        """Triple yakuman (39 han) produces correct payment amount."""
        east_tiles = TilesConverter.string_to_136_array(honors="111")
        closed_tiles = TilesConverter.string_to_136_array(honors="222333444")
        pair_tiles = TilesConverter.string_to_136_array(honors="55")
        all_tiles = tuple(east_tiles) + tuple(closed_tiles) + (pair_tiles[0],)

        east_pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(east_tiles),
            opened=True,
            called_tile=east_tiles[0],
            who=1,
            from_who=0,
        )

        game_state = _make_scoring_game_state()
        win_tile = pair_tiles[1]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles, melds=(east_pon,))
        player = round_state.players[1]

        settings = GameSettings(has_double_yakuman=True)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=False)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert result.han == 39
        # triple yakuman non-dealer ron: base 24000 * 4 = 96000
        assert result.cost_main == 96000


class TestKazoeYakuman:
    """Verify has_kazoe_yakuman setting controls 13+ han non-yakuman scoring."""

    def test_kazoe_yakuman_enabled_caps_at_yakuman(self):
        """Non-yakuman hand with 13+ han pays yakuman-level when kazoe enabled."""
        # chinitsu (6) + pinfu (1) + iipeiko (1) + tanyao (1) + riichi (1) + tsumo (1) = 11 han
        # + 3 dora (5m x 3, indicator 4m) = 14 han, kazoe yakuman
        # The library returns raw han but caps the payment at yakuman level.
        tiles = TilesConverter.string_to_136_array(man="2233445556677")
        win_tile = TilesConverter.string_to_136_array(man="8")[0]
        dora_indicator = TilesConverter.string_to_136_array(man="4444")[3:]  # 4th copy of 4m as indicator
        final_tiles = (*tuple(tiles), win_tile)

        game_state = _make_scoring_game_state(dora_indicators=dora_indicator)
        round_state = update_player(
            game_state.round_state,
            1,
            tiles=final_tiles,
            is_riichi=True,
            discards=(Discard(tile_id=0),),
        )
        player = round_state.players[1]

        settings = GameSettings(has_kazoe_yakuman=True, has_akadora=False, has_uradora=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # raw han exceeds kazoe threshold
        assert result.han >= 13
        # payment is yakuman-level: non-dealer tsumo = dealer pays 16000, non-dealer pays 8000
        assert result.cost_main == 16000
        assert result.cost_additional == 8000

    def test_kazoe_yakuman_disabled_caps_at_sanbaiman(self):
        """Non-yakuman hand with 13+ han pays sanbaiman-level when kazoe disabled."""
        tiles = TilesConverter.string_to_136_array(man="2233445556677")
        win_tile = TilesConverter.string_to_136_array(man="8")[0]
        dora_indicator = TilesConverter.string_to_136_array(man="4444")[3:]
        final_tiles = (*tuple(tiles), win_tile)

        game_state = _make_scoring_game_state(dora_indicators=dora_indicator)
        round_state = update_player(
            game_state.round_state,
            1,
            tiles=final_tiles,
            is_riichi=True,
            discards=(Discard(tile_id=0),),
        )
        player = round_state.players[1]

        settings = GameSettings(has_kazoe_yakuman=False, has_akadora=False, has_uradora=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # raw han still exceeds 13 but payment is capped at sanbaiman
        assert result.han >= 13
        # sanbaiman non-dealer tsumo: dealer pays 12000, non-dealer pays 6000
        assert result.cost_main == 12000
        assert result.cost_additional == 6000

    def test_kazoe_setting_wired_to_library(self):
        """has_kazoe_yakuman maps to kazoe_limit in the library's OptionalRules."""
        rules_enabled = build_optional_rules(GameSettings(has_kazoe_yakuman=True))
        assert rules_enabled.kazoe_limit == HandConfig.KAZOE_LIMITED

        rules_disabled = build_optional_rules(GameSettings(has_kazoe_yakuman=False))
        assert rules_disabled.kazoe_limit == HandConfig.KAZOE_SANBAIMAN

    def test_dora_counts_toward_kazoe_threshold(self):
        """Dora pushes a non-yakuman hand past the kazoe threshold, changing payment level."""
        # chinitsu (6) + pinfu (1) + iipeiko (1) + tanyao (1) + riichi (1) + tsumo (1) = 11 han
        # Without dora: 11 han -> sanbaiman payment
        # With 3 dora: 14 han -> kazoe yakuman payment
        tiles = TilesConverter.string_to_136_array(man="2233445556677")
        win_tile = TilesConverter.string_to_136_array(man="8")[0]
        final_tiles = (*tuple(tiles), win_tile)

        # No dora indicator matching hand tiles -> no dora -> 11 han (sanbaiman)
        no_dora_indicator = TilesConverter.string_to_136_array(pin="1")
        game_state = _make_scoring_game_state(dora_indicators=no_dora_indicator)
        round_state = update_player(
            game_state.round_state,
            1,
            tiles=final_tiles,
            is_riichi=True,
            discards=(Discard(tile_id=0),),
        )
        player = round_state.players[1]

        settings = GameSettings(has_kazoe_yakuman=True, has_akadora=False, has_uradora=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result_no_dora = calculate_hand_value(ctx, win_tile)

        assert result_no_dora.error is None
        # 11 han without dora -> sanbaiman-level payment (not yakuman)
        assert result_no_dora.han < 13
        assert result_no_dora.cost_main == 12000  # sanbaiman dealer payment

        # With dora indicator 4m -> 5m is dora, 3 tiles in hand -> 3 dora -> 14 han
        dora_indicator = TilesConverter.string_to_136_array(man="4444")[3:]
        game_state2 = _make_scoring_game_state(dora_indicators=dora_indicator)
        round_state2 = update_player(
            game_state2.round_state,
            1,
            tiles=final_tiles,
            is_riichi=True,
            discards=(Discard(tile_id=0),),
        )
        player2 = round_state2.players[1]

        ctx2 = ScoringContext(player=player2, round_state=round_state2, settings=settings, is_tsumo=True)
        result_with_dora = calculate_hand_value(ctx2, win_tile)

        assert result_with_dora.error is None
        # dora pushes hand past kazoe threshold -> yakuman-level payment
        assert result_with_dora.han >= 13
        assert result_with_dora.cost_main == 16000  # yakuman dealer payment


class TestYakumanDoraInteraction:
    """Verify that dora does not add han to yakuman hands."""

    def test_dora_does_not_add_to_yakuman(self):
        """Yakuman hand with matching dora tiles still scores at yakuman han, not higher."""
        # suuankou tanki (26 han double yakuman) with dora indicator 0m -> 1m is dora
        # hand has 3x 1m, so 3 dora would normally add 3 han, but yakuman ignores dora
        tiles = TilesConverter.string_to_136_array(man="111", pin="333", sou="555777")
        pair_tiles = TilesConverter.string_to_136_array(sou="99")
        all_tiles = (*tuple(tiles), pair_tiles[0])

        # dora indicator 9m -> dora is 1m (3 copies in hand)
        dora_indicator = TilesConverter.string_to_136_array(man="9999")[3:]
        game_state = _make_scoring_game_state(dora_indicators=dora_indicator)
        win_tile = pair_tiles[1]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles)
        player = round_state.players[1]

        settings = GameSettings(has_double_yakuman=True)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # han is still 26 (double yakuman), not 26 + 3 dora
        assert result.han == 26

    def test_yakuman_yaku_list_excludes_dora(self):
        """Yakuman hand's yaku list contains only yakuman yaku, no dora yaku."""
        tiles = TilesConverter.string_to_136_array(man="111", pin="333", sou="555777")
        pair_tiles = TilesConverter.string_to_136_array(sou="99")
        all_tiles = (*tuple(tiles), pair_tiles[0])

        # dora indicator that matches tiles in hand
        dora_indicator = TilesConverter.string_to_136_array(man="9999")[3:]
        game_state = _make_scoring_game_state(dora_indicators=dora_indicator)
        win_tile = pair_tiles[1]
        final_tiles = (*all_tiles, win_tile)
        round_state = update_player(game_state.round_state, 1, tiles=final_tiles)
        player = round_state.players[1]

        settings = GameSettings()
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        yaku_ids = {y.yaku_id for y in result.yaku}
        # yaku_id 120 = dora, 121 = aka dora, 122 = ura dora
        assert 120 not in yaku_ids, "Dora should not appear in yakuman yaku list"
        assert 121 not in yaku_ids, "Aka dora should not appear in yakuman yaku list"
        assert 122 not in yaku_ids, "Ura dora should not appear in yakuman yaku list"

    def test_non_yakuman_hand_includes_dora(self):
        """Non-yakuman hand correctly includes dora in its han count (control test)."""
        # simple riichi + tsumo hand with dora
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        win_tile = tiles[-1]

        # dora indicator 4p -> 5p is dora (2 copies in hand)
        dora_indicator = TilesConverter.string_to_136_array(pin="4444")[3:]
        game_state = _make_scoring_game_state(dora_indicators=dora_indicator)
        round_state = update_player(
            game_state.round_state,
            1,
            tiles=tuple(tiles),
            is_riichi=True,
            discards=(Discard(tile_id=0),),
        )
        player = round_state.players[1]

        settings = GameSettings(has_akadora=False)
        ctx = ScoringContext(player=player, round_state=round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        # yaku_id 120 = dora should be present
        assert any(y.yaku_id == 120 for y in result.yaku), "Non-yakuman hand should include dora"


class TestSextupleYakumanLimit:
    """Verify limit_to_sextuple_yakuman setting controls maximum yakuman stacking."""

    def test_setting_wired_to_optional_rules(self):
        """limit_to_sextuple_yakuman maps to the library's OptionalRules."""
        rules_enabled = build_optional_rules(GameSettings(limit_to_sextuple_yakuman=True))
        assert rules_enabled.limit_to_sextuple_yakuman is True

        rules_disabled = build_optional_rules(GameSettings(limit_to_sextuple_yakuman=False))
        assert rules_disabled.limit_to_sextuple_yakuman is False
