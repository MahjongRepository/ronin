"""
Tests for abortive draw settings thresholds and process_abortive_draw.

Core detection logic (qualifying hands, boundary conditions, guard clauses)
is covered by test_abortive.py. This file focuses on configurable thresholds
and abortive draw processing.
"""

from mahjong.tile import TilesConverter

from game.logic.abortive import (
    AbortiveDrawType,
    can_call_kyuushu_kyuuhai,
    check_four_winds,
    check_triple_ron,
    process_abortive_draw,
)
from game.logic.enums import RoundResultType
from game.logic.settings import GameSettings
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.tests.conftest import create_game_state, create_player, create_round_state


class TestKyuushuKyuuhaiThresholds:
    """Verify kyuushu_min_types threshold customization."""

    def _round_state_with_hand(self, tiles):
        """Fresh round state with player holding specific tiles, no discards/melds."""
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"P{i}",
                tiles=tuple(tiles) if i == 0 else (),
                score=25000,
            )
            for i in range(4)
        )
        return MahjongRoundState(players=players, current_player_seat=0)

    def test_custom_threshold_lower(self):
        """With kyuushu_min_types=8, a hand with 8 types qualifies."""
        tiles = [
            *TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="12"),
            *TilesConverter.string_to_136_array(man="223345"),
        ]
        rs = self._round_state_with_hand(tiles)
        settings_default = GameSettings(kyuushu_min_types=9)
        settings_custom = GameSettings(kyuushu_min_types=8)

        assert can_call_kyuushu_kyuuhai(rs.players[0], rs, settings_default) is False
        assert can_call_kyuushu_kyuuhai(rs.players[0], rs, settings_custom) is True

    def test_custom_threshold_higher(self):
        """With kyuushu_min_types=10, a hand with 9 types does not qualify."""
        tiles = [
            *TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123"),
            *TilesConverter.string_to_136_array(man="22334"),
        ]
        rs = self._round_state_with_hand(tiles)
        settings = GameSettings(kyuushu_min_types=10)
        assert can_call_kyuushu_kyuuhai(rs.players[0], rs, settings) is False


class TestFourWindsThresholds:
    """Verify four_winds_discard_count threshold customization."""

    def test_custom_discard_count(self):
        """With four_winds_discard_count=3, 3 same wind discards triggers."""
        east_tiles = TilesConverter.string_to_136_array(honors="111")[:3]
        rs = MahjongRoundState(
            players=tuple(MahjongPlayer(seat=i, name=f"P{i}", score=25000) for i in range(4)),
            all_discards=tuple(east_tiles),
        )
        settings_default = GameSettings(four_winds_discard_count=4)
        settings_custom = GameSettings(four_winds_discard_count=3)

        assert check_four_winds(rs, settings_default) is False
        assert check_four_winds(rs, settings_custom) is True


class TestTripleRonThresholds:
    """Verify triple_ron_count threshold customization."""

    def test_custom_triple_ron_count(self):
        """With triple_ron_count=2, two callers triggers abortive draw."""
        assert check_triple_ron([0, 2], 2) is True


class TestProcessAbortiveDraw:
    """Verify abortive draw processing: no score changes, correct result type."""

    def test_no_score_changes(self):
        """Abortive draw produces zero score changes for all players."""
        game_state = create_game_state()
        result = process_abortive_draw(game_state, AbortiveDrawType.NINE_TERMINALS)
        assert all(v == 0 for v in result.score_changes.values())
        assert result.type == RoundResultType.ABORTIVE_DRAW

    def test_scores_preserved(self):
        """Abortive draw preserves current scores."""
        players = tuple(create_player(seat=i, score=25000 + i * 1000) for i in range(4))
        rs = create_round_state(players=players)
        game_state = create_game_state(round_state=rs)
        result = process_abortive_draw(game_state, AbortiveDrawType.FOUR_WINDS)
        assert result.scores[0] == 25000
        assert result.scores[1] == 26000
        assert result.scores[2] == 27000
        assert result.scores[3] == 28000

    def test_each_draw_type_produces_correct_reason(self):
        """Each AbortiveDrawType produces a result with the correct reason."""
        game_state = create_game_state()
        for draw_type in AbortiveDrawType:
            result = process_abortive_draw(game_state, draw_type)
            assert result.reason == draw_type
