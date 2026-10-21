from mahjong.tile import TilesConverter

from game.logic.scoring import (
    ScoringContext,
    calculate_hand_value,
    collect_ura_dora_indicators,
)
from game.logic.settings import GameSettings
from game.tests.conftest import create_game_state, create_player, create_round_state

# Yaku IDs from the mahjong library
DORA_YAKU_ID = 120
AKA_DORA_YAKU_ID = 121
URA_DORA_YAKU_ID = 122


def _dora_han(result, yaku_id):
    for y in result.yaku:
        if y.yaku_id == yaku_id:
            return y.han

    return 0


def _build_scoring_state(*, tiles, dora_indicators, is_riichi=False, dead_wall=None):
    tenhou_blocking_discards = TilesConverter.string_to_136_array(man="1112")

    if dead_wall is None:
        dead_wall = tuple(range(14))

    players = (
        create_player(seat=0, tiles=tuple(tiles), is_riichi=is_riichi),
        create_player(seat=1),
        create_player(seat=2),
        create_player(seat=3),
    )
    round_state = create_round_state(
        players=players,
        dealer_seat=0,
        current_player_seat=0,
        dora_indicators=tuple(dora_indicators),
        dead_wall=dead_wall,
        wall=tuple(range(70)),
        all_discards=tenhou_blocking_discards,
    )
    return create_game_state(round_state=round_state)


def _base_hand():
    return TilesConverter.string_to_136_array(man="123456789", sou="12355")


class TestIndicatorToDoraMappingSuited:
    settings = GameSettings(has_akadora=False)

    def test_dora_indicator__when_9m__should_make_1m_dora(self):
        tiles = _base_hand()
        win_tile = tiles[-1]
        # 9m indicator -> dora is 1m (1 copy in hand)
        indicator = TilesConverter.string_to_136_array(man="9")

        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=self.settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, DORA_YAKU_ID) == 1

    def test_dora_indicator__when_4s__should_make_5s_dora(self):
        tiles = _base_hand()
        win_tile = tiles[-1]
        # 4s indicator -> dora is 5s (2 copies in hand = 2 dora)
        indicator = TilesConverter.string_to_136_array(sou="4")

        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=self.settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, DORA_YAKU_ID) == 2

    def test_dora_indicator__when_9s__should_wrap_to_1s_dora(self):
        tiles = _base_hand()
        win_tile = tiles[-1]
        # 9s indicator -> dora is 1s (1 copy in hand)
        indicator = TilesConverter.string_to_136_array(sou="9")

        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=self.settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, DORA_YAKU_ID) == 1


class TestIndicatorToDoraMappingWinds:
    settings = GameSettings(has_akadora=False)

    def test_dora_indicator__when_north__should_make_east_dora(self):
        # Hand: 123m 456m 789p 123s EE (pair of East)
        tiles = TilesConverter.string_to_136_array(man="123456", pin="789", sou="123", honors="11")
        win_tile = tiles[-1]
        # North (honors=4) indicator -> dora is East (2 copies = 2 dora)
        indicator = TilesConverter.string_to_136_array(honors="4")

        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=self.settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, DORA_YAKU_ID) == 2

    def test_dora_indicator__when_east__should_make_south_dora(self):
        # Hand: 123m 456m 789p 123s SS (pair of South)
        tiles = TilesConverter.string_to_136_array(man="123456", pin="789", sou="123", honors="22")
        win_tile = tiles[-1]
        # East (honors=1) indicator -> dora is South (2 copies = 2 dora)
        indicator = TilesConverter.string_to_136_array(honors="1")

        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=self.settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, DORA_YAKU_ID) == 2


class TestIndicatorToDoraMappingDragons:
    settings = GameSettings(has_akadora=False)

    def test_dora_indicator__when_chun__should_wrap_to_haku_dora(self):
        # Hand: 123m 456m 789p 123s HakuHaku (pair)
        tiles = TilesConverter.string_to_136_array(man="123456", pin="789", sou="123", honors="55")
        win_tile = tiles[-1]
        # Chun (honors=7) indicator -> dora is Haku (2 copies = 2 dora)
        indicator = TilesConverter.string_to_136_array(honors="7")

        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=self.settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, DORA_YAKU_ID) == 2

    def test_dora_indicator__when_haku__should_make_hatsu_dora(self):
        # Hand with HatsuHatsu pair
        tiles = TilesConverter.string_to_136_array(man="123456", pin="789", sou="123", honors="66")
        win_tile = tiles[-1]
        # Haku (honors=5) indicator -> dora is Hatsu (2 copies = 2 dora)
        indicator = TilesConverter.string_to_136_array(honors="5")

        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=self.settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, DORA_YAKU_ID) == 2


class TestRedFiveAkadora:
    def test_akadora__when_red_five_in_hand__should_count_one_han(self):
        # Hand: 11m 34r(5red)m 678m 123p 789s (14 tiles, closed)
        # Use 'r' to explicitly request the red five tile (tile ID 16)
        tiles = TilesConverter.string_to_136_array(man="1134r678", pin="123", sou="789", has_aka_dora=True)
        win_tile = tiles[-1]
        # Indicator not pointing to 5m (1s indicator -> dora is 2s)
        indicator = TilesConverter.string_to_136_array(sou="1")

        settings = GameSettings(has_akadora=True)
        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, AKA_DORA_YAKU_ID) == 1

    def test_akadora__when_red_five_is_also_dora__should_stack_with_dora(self):
        # Hand with red 5m: 11m 34r(5red)m 678m 123p 789s (using 'r' for red tile)
        tiles = TilesConverter.string_to_136_array(man="1134r678", pin="123", sou="789", has_aka_dora=True)
        win_tile = tiles[-1]
        # Indicator: 4m -> dora is 5m
        # Red 5m = 1 (aka dora) + 1 (indicator dora) = total 2 dora across two yaku types
        indicator = TilesConverter.string_to_136_array(man="4")

        settings = GameSettings(has_akadora=True)
        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        # 1 from indicator (5m tile type matches)
        assert _dora_han(result, DORA_YAKU_ID) == 1
        # 1 from aka dora (red five tile ID)
        assert _dora_han(result, AKA_DORA_YAKU_ID) == 1

    def test_akadora__when_disabled__should_not_count_red_five(self):
        # Even though tile ID 16 (red 5m) is in the hand, aka dora is disabled
        tiles = TilesConverter.string_to_136_array(man="1134r678", pin="123", sou="789", has_aka_dora=True)
        win_tile = tiles[-1]
        indicator = TilesConverter.string_to_136_array(sou="1")

        settings = GameSettings(has_akadora=False)
        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, AKA_DORA_YAKU_ID) == 0

    def test_akadora__when_all_three_red_fives__should_count_three_han(self):
        # Hand: 11m 34r(red5)m 34r(red5)p 34r(red5)s EEE (14 tiles)
        # Use 'r' in each suit to get the red five
        tiles = TilesConverter.string_to_136_array(
            man="1134r",
            pin="34r",
            sou="34r",
            honors="111",
            has_aka_dora=True,
        )
        win_tile = tiles[-1]
        # Indicator not pointing to any 5
        indicator = TilesConverter.string_to_136_array(man="1")

        settings = GameSettings(has_akadora=True)
        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, AKA_DORA_YAKU_ID) == 3


class TestUraDoraRevelation:
    settings_no_aka = GameSettings(has_akadora=False)

    def test_ura_dora__when_double_riichi_winner__should_reveal_indicator(self):
        dead_wall = tuple(range(100, 114))
        settings = GameSettings(has_uradora=True)
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
        )
        player = create_player(seat=0, is_riichi=True, is_daburi=True)

        result = collect_ura_dora_indicators(player, round_state, settings=settings)
        assert result == [dead_wall[7]]

    def test_ura_dora__when_riichi_tsumo__should_add_han(self):
        tiles = _base_hand()
        win_tile = tiles[-1]

        # Dora indicator: 2m -> dora is 3m (1 in hand)
        dora_ind = TilesConverter.string_to_136_array(man="2")
        # Ura dora indicator: 4s -> ura dora is 5s (2 in hand = 2 ura dora)
        ura_ind = TilesConverter.string_to_136_array(sou="4")[0]

        dead_wall = [0] * 14
        dead_wall[2] = dora_ind[0]
        dead_wall[7] = ura_ind

        game_state = _build_scoring_state(
            tiles=tiles,
            dora_indicators=dora_ind,
            is_riichi=True,
            dead_wall=tuple(dead_wall),
        )
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=self.settings_no_aka,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, URA_DORA_YAKU_ID) == 2

    def test_ura_dora__when_not_riichi__should_add_no_han(self):
        tiles = _base_hand()
        win_tile = tiles[-1]

        dora_ind = TilesConverter.string_to_136_array(man="2")
        ura_ind = TilesConverter.string_to_136_array(sou="4")[0]

        dead_wall = [0] * 14
        dead_wall[2] = dora_ind[0]
        dead_wall[7] = ura_ind

        game_state = _build_scoring_state(
            tiles=tiles,
            dora_indicators=dora_ind,
            is_riichi=False,
            dead_wall=tuple(dead_wall),
        )
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=self.settings_no_aka,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, URA_DORA_YAKU_ID) == 0

    def test_ura_dora__when_disabled__should_add_no_han(self):
        tiles = _base_hand()
        win_tile = tiles[-1]

        dora_ind = TilesConverter.string_to_136_array(man="2")
        ura_ind = TilesConverter.string_to_136_array(sou="4")[0]

        dead_wall = [0] * 14
        dead_wall[2] = dora_ind[0]
        dead_wall[7] = ura_ind

        settings = GameSettings(has_akadora=False, has_uradora=False)
        game_state = _build_scoring_state(
            tiles=tiles,
            dora_indicators=dora_ind,
            is_riichi=True,
            dead_wall=tuple(dead_wall),
        )
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert _dora_han(result, URA_DORA_YAKU_ID) == 0
