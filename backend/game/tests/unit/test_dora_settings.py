from mahjong.tile import TilesConverter

from game.logic.scoring import (
    ScoringContext,
    _collect_dora_indicators,
    calculate_hand_value,
    collect_ura_dora_indicators,
)
from game.logic.settings import GameSettings
from game.logic.wall import add_dora_indicator
from game.logic.wall import collect_ura_dora_indicators as wall_collect_ura_dora
from game.tests.conftest import create_game_state, create_player, create_round_state
from game.tests.helpers.wall import FIRST_URA_POSITION, make_wall

DORA_YAKU_ID = 120
URA_DORA_YAKU_ID = 122


def _dora_han(result, yaku_id):
    for y in result.yaku:
        if y.yaku_id == yaku_id:
            return y.han

    return 0


def _build_scoring_state(*, tiles, dora_indicators, is_riichi=False, dead_wall=None):
    dummy_discard_tiles = TilesConverter.string_to_136_array(man="1112")

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
        all_discards=dummy_discard_tiles,
    )
    return create_game_state(round_state=round_state)


def _base_hand():
    return TilesConverter.string_to_136_array(man="123456789", sou="12355")


class TestOmoteDoraSetting:
    def test_omote_dora__when_enabled__should_score_dora_han(self):
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

    def test_omote_dora__when_disabled__should_score_no_dora_han(self):
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

    def test_collect_dora_indicators__when_omote_enabled__should_return_indicators(self):
        settings = GameSettings(has_omote_dora=True)
        round_state = create_round_state(dora_indicators=(10, 20, 30))

        result = _collect_dora_indicators(round_state, settings)
        assert result == [10, 20, 30]

    def test_collect_dora_indicators__when_omote_disabled__should_return_empty(self):
        settings = GameSettings(has_omote_dora=False)
        round_state = create_round_state(dora_indicators=(10, 20, 30))

        result = _collect_dora_indicators(round_state, settings)
        assert result == []


class TestUraDoraSettingGating:
    def test_ura_dora__when_enabled_and_riichi__should_score_ura_han(self):
        tiles = _base_hand()
        win_tile = tiles[-1]

        dora_ind = TilesConverter.string_to_136_array(man="2")
        # 4s -> ura dora is 5s (2 copies in hand)
        ura_ind = TilesConverter.string_to_136_array(sou="4")[0]

        dead_wall: list[int | None] = [None] * 14
        dead_wall[2] = dora_ind[0]
        dead_wall[FIRST_URA_POSITION] = ura_ind

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

    def test_ura_dora__when_disabled_and_riichi__should_score_no_ura_han(self):
        tiles = _base_hand()
        win_tile = tiles[-1]

        dora_ind = TilesConverter.string_to_136_array(man="2")
        ura_ind = TilesConverter.string_to_136_array(sou="4")[0]

        dead_wall: list[int | None] = [None] * 14
        dead_wall[2] = dora_ind[0]
        dead_wall[FIRST_URA_POSITION] = ura_ind

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


class TestKanDoraSetting:
    def test_kan_dora__when_enabled__should_add_indicator(self):
        dead_wall = tuple(range(100, 114))
        wall = make_wall(
            live_tiles=tuple(range(50)),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
        )
        # Simulate immediate dora reveal (closed kan path)
        new_wall, indicator = add_dora_indicator(wall)
        assert len(new_wall.dora_indicators) == 2
        assert indicator == dead_wall[3]


class TestKanUraDoraSettingGating:
    def test_kan_ura_dora__when_enabled__should_reveal_indicator_per_kan(self):
        dead_wall = tuple(range(100, 114))
        wall = make_wall(
            live_tiles=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3]),
        )
        result = wall_collect_ura_dora(wall, include_kan_ura=True)
        assert result == [dead_wall[FIRST_URA_POSITION], dead_wall[FIRST_URA_POSITION + 1]]

    def test_kan_ura_dora__when_disabled__should_reveal_single_indicator(self):
        dead_wall = tuple(range(100, 114))
        wall = make_wall(
            live_tiles=(),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3]),
        )
        result = wall_collect_ura_dora(wall, include_kan_ura=False)
        assert result == [dead_wall[FIRST_URA_POSITION]]

    def test_collect_ura_dora_indicators__when_two_dora_indicators__should_reveal_two_with_kan_ura_and_one_without(
        self,
    ):
        dead_wall = tuple(range(100, 114))
        round_state = create_round_state(
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2], dead_wall[3]),
        )
        player = create_player(seat=0, is_riichi=True)

        result_enabled = collect_ura_dora_indicators(
            player,
            round_state,
            settings=GameSettings(has_uradora=True, has_kan_uradora=True),
        )
        result_disabled = collect_ura_dora_indicators(
            player,
            round_state,
            settings=GameSettings(has_uradora=True, has_kan_uradora=False),
        )
        assert len(result_enabled) == 2
        assert len(result_disabled) == 1
