from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import ScoringContext, calculate_hand_value
from game.logic.settings import GameSettings
from game.logic.state import Discard
from game.logic.state_utils import update_player
from game.tests.conftest import create_game_state, create_player, create_round_state


def _make_scoring_game_state(
    *,
    dealer_seat: int = 0,
    dora_indicators=None,
    settings: GameSettings | None = None,
):
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
        all_discards=TilesConverter.string_to_136_array(man="1112"),
    )
    return create_game_state(round_state=round_state, settings=settings)


class TestDoubleYakumanSetting:
    def test_double_yakuman_setting__when_disabled__should_score_single_yakuman(self):
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

    def test_daisuushii_setting__when_double_disabled__should_score_single_yakuman(self):
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


class TestYakumanStacking:
    def test_yakuman_stacking__when_daisuushii_and_tsuuiisou__should_stack(self):
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

    def test_yakuman_stacking__when_double_yakuman_disabled__should_stack_single_values(self):
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

    def test_yakuman_stacking__when_stacked__should_pay_multiple_yakuman(self):
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
    def test_kazoe_yakuman__when_enabled__should_cap_at_yakuman(self):
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

    def test_kazoe_yakuman__when_disabled__should_cap_at_sanbaiman(self):
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

    def test_kazoe_yakuman__when_dora_lifts_han_to_13__should_score_yakuman(self):
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
    def test_yakuman_dora__when_yakuman_hand_has_dora__should_not_add_han(self):
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

    def test_yakuman_dora__when_yakuman_hand_has_dora__should_exclude_dora_from_yaku_list(self):
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

    def test_yakuman_dora__when_non_yakuman_hand__should_include_dora_yaku(self):
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
