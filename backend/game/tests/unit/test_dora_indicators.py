"""
Tests for dora indicator rules: indicator-to-dora mapping, red fives (akadora),
and ura dora revelation conditions.

Verifies end-to-end dora behavior through the scoring system, confirming
the mahjong library's indicator mapping works correctly with our scoring code.
"""

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
    """Extract han for a specific dora yaku from hand result, or 0 if absent."""
    for y in result.yaku:
        if y.yaku_id == yaku_id:
            return y.han
    return 0


def _build_scoring_state(*, tiles, dora_indicators, is_riichi=False, dead_wall=None):
    """Build a game state for dora scoring tests.

    Uses a mid-game state (discards present, non-empty wall) to avoid
    Tenhou/Chiihou triggering. Places dora indicators explicitly.
    """
    dummy_discard_tiles = TilesConverter.string_to_136_array(man="1112")
    if dead_wall is None:
        dead_wall = tuple(range(14))

    players = tuple(
        create_player(
            seat=i,
            tiles=tuple(tiles) if i == 0 else None,
            is_riichi=is_riichi if i == 0 else False,
        )
        for i in range(4)
    )
    round_state = create_round_state(
        players=players,
        dealer_seat=0,
        current_player_seat=0,
        dora_indicators=tuple(dora_indicators),
        dead_wall=dead_wall,
        wall=tuple(range(70)),
        all_discards=dummy_discard_tiles,
    )
    return create_game_state(round_state=round_state)


def _base_hand():
    """Base hand: 123m 456m 789m 123s 55s (ittsu, closed, 14 tiles)."""
    return TilesConverter.string_to_136_array(man="123456789", sou="12355")


class TestIndicatorToDoraMappingSuited:
    """Verify suited tile indicator wrapping: 1->2->...->9->1."""

    settings = GameSettings(has_akadora=False)

    def test_9m_indicator_makes_1m_dora(self):
        """Indicator 9m wraps to dora 1m: hand with 1m gets 1 dora."""
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

    def test_4s_indicator_makes_5s_dora(self):
        """Indicator 4s makes 5s dora: hand with two 5s gets 2 dora."""
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

    def test_9s_indicator_wraps_to_1s(self):
        """Indicator 9s wraps to dora 1s: verifies sou suit wrapping."""
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
    """Verify wind tile indicator wrapping: E->S->W->N->E."""

    settings = GameSettings(has_akadora=False)

    def test_north_indicator_makes_east_dora(self):
        """Indicator North wraps to dora East: N->E in wind cycle."""
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

    def test_east_indicator_makes_south_dora(self):
        """Indicator East makes South the dora: E->S in wind cycle."""
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
    """Verify dragon tile indicator wrapping: Haku->Hatsu->Chun->Haku."""

    settings = GameSettings(has_akadora=False)

    def test_chun_indicator_wraps_to_haku_dora(self):
        """Indicator Chun wraps to dora Haku: Chun->Haku in dragon cycle."""
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

    def test_haku_indicator_makes_hatsu_dora(self):
        """Indicator Haku makes Hatsu the dora: Haku->Hatsu in dragon cycle."""
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
    """Verify red fives (akadora) are inherently 1 dora each, independent of indicators."""

    def test_red_five_man_inherent_dora(self):
        """Red 5m is 1 aka dora even with no indicator pointing to 5m."""
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

    def test_red_five_plus_indicator_stacks_to_two_dora(self):
        """Red 5m with indicator 4m gives 2 total dora: 1 inherent (aka) + 1 from indicator."""
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

    def test_akadora_disabled_no_inherent_dora(self):
        """With has_akadora=False, red five tiles do not contribute aka dora."""
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

    def test_all_three_red_fives(self):
        """Hand with all three red fives (5m, 5p, 5s) gets 3 aka dora."""
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
    """Verify ura dora is revealed only for riichi/double riichi winners."""

    settings_no_aka = GameSettings(has_akadora=False)

    def test_double_riichi_winner_gets_ura_dora(self):
        """Double riichi (daburi) winner receives ura dora indicators."""
        dead_wall = tuple(range(100, 114))
        settings = GameSettings(has_uradora=True)
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
        )
        player = create_player(seat=0, is_riichi=True, is_daburi=True)
        result = collect_ura_dora_indicators(player, round_state, settings)
        assert result == [dead_wall[7]]

    def test_ura_dora_adds_han_for_riichi_tsumo(self):
        """Ura dora indicator matching hand tiles adds han for riichi winner."""
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

    def test_non_riichi_gets_no_ura_dora(self):
        """Non-riichi winner does not receive ura dora even when matching tiles exist."""
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

    def test_ura_dora_disabled_setting(self):
        """With has_uradora=False, riichi winner gets no ura dora."""
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
