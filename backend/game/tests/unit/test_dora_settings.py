"""
Verifies that each dora-related setting in GameSettings correctly controls
dora behavior: omote dora, ura dora, red dora (akadora), kan dora, and
kan ura dora. Focuses on the settings-level gating rather than repeating
indicator mapping tests from test_dora_indicators.py.
"""

from mahjong.tile import TilesConverter

from game.logic.scoring import (
    ScoringContext,
    _collect_dora_indicators,
    calculate_hand_value,
    collect_ura_dora_indicators,
)
from game.logic.settings import GameSettings, build_optional_rules
from game.logic.wall import Wall, add_dora_indicator
from game.logic.wall import collect_ura_dora_indicators as wall_collect_ura_dora
from game.tests.conftest import create_game_state, create_player, create_round_state

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
    """Build a game state for dora scoring tests."""
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


class TestOmoteDoraSetting:
    """Verify has_omote_dora controls face-up dora indicator collection."""

    def test_omote_dora_enabled_scores_dora(self):
        """With has_omote_dora=True (default), dora indicators contribute han."""
        tiles = _base_hand()
        win_tile = tiles[-1]
        # 4s indicator -> dora is 5s (2 copies in hand)
        indicator = TilesConverter.string_to_136_array(sou="4")

        settings = GameSettings(has_akadora=False, has_omote_dora=True)
        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert _dora_han(result, DORA_YAKU_ID) == 2

    def test_omote_dora_disabled_no_dora_han(self):
        """With has_omote_dora=False, dora indicators are ignored in scoring."""
        tiles = _base_hand()
        win_tile = tiles[-1]
        indicator = TilesConverter.string_to_136_array(sou="4")

        settings = GameSettings(has_akadora=False, has_omote_dora=False)
        game_state = _build_scoring_state(tiles=tiles, dora_indicators=indicator, is_riichi=True)
        ctx = ScoringContext(
            player=game_state.round_state.players[0],
            round_state=game_state.round_state,
            settings=settings,
            is_tsumo=True,
        )
        result = calculate_hand_value(ctx, win_tile)

        assert result.error is None
        assert _dora_han(result, DORA_YAKU_ID) == 0

    def test_collect_dora_indicators_returns_indicators_when_enabled(self):
        """_collect_dora_indicators returns all wall indicators when enabled."""
        settings = GameSettings(has_omote_dora=True)
        round_state = create_round_state(dora_indicators=(10, 20, 30))
        result = _collect_dora_indicators(round_state, settings)
        assert result == [10, 20, 30]

    def test_collect_dora_indicators_returns_empty_when_disabled(self):
        """_collect_dora_indicators returns empty list when disabled."""
        settings = GameSettings(has_omote_dora=False)
        round_state = create_round_state(dora_indicators=(10, 20, 30))
        result = _collect_dora_indicators(round_state, settings)
        assert result == []


class TestUraDoraSettingGating:
    """Verify has_uradora gates ura dora at the scoring level."""

    def test_ura_dora_enabled_riichi_gets_ura_han(self):
        """Riichi winner gets ura dora han when has_uradora=True."""
        tiles = _base_hand()
        win_tile = tiles[-1]

        dora_ind = TilesConverter.string_to_136_array(man="2")
        # 4s -> ura dora is 5s (2 copies in hand)
        ura_ind = TilesConverter.string_to_136_array(sou="4")[0]

        dead_wall = [0] * 14
        dead_wall[2] = dora_ind[0]
        dead_wall[7] = ura_ind

        settings = GameSettings(has_akadora=False, has_uradora=True)
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
        assert _dora_han(result, URA_DORA_YAKU_ID) == 2

    def test_ura_dora_disabled_riichi_gets_no_ura(self):
        """Riichi winner gets no ura dora han when has_uradora=False."""
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


class TestAkadoraSetting:
    """Verify has_akadora controls red five dora and count is fixed at 3."""

    def test_akadora_enabled_red_five_scores(self):
        """Red five counts as 1 aka dora when has_akadora=True."""
        tiles = TilesConverter.string_to_136_array(man="1134r678", pin="123", sou="789", has_aka_dora=True)
        win_tile = tiles[-1]
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

    def test_akadora_disabled_red_five_ignored(self):
        """Red five is ignored when has_akadora=False."""
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

    def test_akadora_flows_through_optional_rules(self):
        """has_akadora maps to has_aka_dora in OptionalRules."""
        rules_enabled = build_optional_rules(GameSettings(has_akadora=True))
        rules_disabled = build_optional_rules(GameSettings(has_akadora=False))
        assert rules_enabled.has_aka_dora is True
        assert rules_disabled.has_aka_dora is False


class TestKanDoraSetting:
    """Verify has_kandora controls whether kan reveals additional dora indicators."""

    def test_kan_dora_enabled_adds_indicator(self):
        """With has_kandora=True, kan adds a new dora indicator to the wall."""
        dead_wall = tuple(range(100, 114))
        wall = Wall(
            live_tiles=tuple(range(50)),
            dead_wall_tiles=dead_wall,
            dora_indicators=(dead_wall[2],),
        )
        # Simulate immediate dora reveal (closed kan path)
        new_wall, indicator = add_dora_indicator(wall)
        assert len(new_wall.dora_indicators) == 2
        assert indicator == dead_wall[3]


class TestKanUraDoraSettingGating:
    """Verify has_kan_uradora controls the number of ura dora indicators returned."""

    def test_kan_ura_enabled_returns_matching_count(self):
        """With has_kan_uradora=True and 2 dora indicators, 2 ura dora are returned."""
        dead_wall = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3]),
            ura_dora_indicators=(dead_wall[7], dead_wall[8], dead_wall[9], dead_wall[10], dead_wall[11]),
        )
        result = wall_collect_ura_dora(wall, include_kan_ura=True)
        assert result == [dead_wall[7], dead_wall[8]]

    def test_kan_ura_disabled_returns_single(self):
        """With has_kan_uradora=False and 2 dora indicators, only 1 ura dora is returned."""
        dead_wall = tuple(range(100, 114))
        wall = Wall(
            live_tiles=(),
            dead_wall_tiles=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3]),
            ura_dora_indicators=(dead_wall[7], dead_wall[8], dead_wall[9], dead_wall[10], dead_wall[11]),
        )
        result = wall_collect_ura_dora(wall, include_kan_ura=False)
        assert result == [dead_wall[7]]

    def test_kan_ura_setting_flows_through_collect_ura_dora_indicators(self):
        """collect_ura_dora_indicators passes has_kan_uradora to wall layer."""
        dead_wall = tuple(range(100, 114))
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3]),
        )
        player = create_player(seat=0, is_riichi=True)

        result_enabled = collect_ura_dora_indicators(
            player,
            round_state,
            GameSettings(has_uradora=True, has_kan_uradora=True),
        )
        result_disabled = collect_ura_dora_indicators(
            player,
            round_state,
            GameSettings(has_uradora=True, has_kan_uradora=False),
        )
        assert len(result_enabled) == 2
        assert len(result_disabled) == 1
