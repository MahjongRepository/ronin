"""
Verifies that each abortive draw type has proper settings toggles and
configurable thresholds: Kyuushu Kyuuhai, Four Winds, Four Riichi, and
Triple Ron. Focuses on settings-level gating and threshold customization
rather than repeating detection tests from test_abortive.py.
"""

from mahjong.tile import TilesConverter

from game.logic.abortive import (
    AbortiveDrawType,
    can_call_kyuushu_kyuuhai,
    check_four_riichi,
    check_four_winds,
    check_triple_ron,
    process_abortive_draw,
)
from game.logic.enums import RoundResultType
from game.logic.meld_wrapper import FrozenMeld
from game.logic.settings import GameSettings
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.tests.conftest import create_game_state, create_player, create_round_state

# ---------------------------------------------------------------------------
# Kyuushu Kyuuhai
# ---------------------------------------------------------------------------


class TestKyuushuKyuuhaiSettings:
    """Verify has_kyuushu_kyuuhai toggle and kyuushu_min_types threshold."""

    def _kyuushu_hand(self):
        """Hand with 9 unique terminal/honor types (1m,9m,1p,9p,1s,9s,E,S,W)."""
        return [
            *TilesConverter.string_to_136_array(man="19", pin="19", sou="19", honors="123"),
            *TilesConverter.string_to_136_array(man="22334"),
        ]

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

    def test_enabled_with_qualifying_hand(self):
        """Kyuushu allowed when setting is enabled and hand qualifies."""
        tiles = self._kyuushu_hand()
        rs = self._round_state_with_hand(tiles)
        settings = GameSettings(has_kyuushu_kyuuhai=True)
        assert can_call_kyuushu_kyuuhai(rs.players[0], rs, settings) is True

    def test_custom_threshold_lower(self):
        """With kyuushu_min_types=8, a hand with 8 types qualifies."""
        # Hand with 8 unique terminal/honor types
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
        tiles = self._kyuushu_hand()
        rs = self._round_state_with_hand(tiles)
        settings = GameSettings(kyuushu_min_types=10)
        assert can_call_kyuushu_kyuuhai(rs.players[0], rs, settings) is False

    def test_any_call_removes_eligibility(self):
        """Closed kan (any meld) by any player blocks kyuushu."""
        tiles = self._kyuushu_hand()
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(pin="1111")),
            opened=False,
        )
        players = (
            MahjongPlayer(seat=0, name="P0", tiles=tuple(tiles), score=25000),
            MahjongPlayer(seat=1, name="P1", tiles=(), melds=(closed_kan,), score=25000),
            MahjongPlayer(seat=2, name="P2", tiles=(), score=25000),
            MahjongPlayer(seat=3, name="P3", tiles=(), score=25000),
        )
        rs = MahjongRoundState(players=players, current_player_seat=0)
        settings = GameSettings()
        assert can_call_kyuushu_kyuuhai(rs.players[0], rs, settings) is False


# ---------------------------------------------------------------------------
# Four Winds (Suufon Renda)
# ---------------------------------------------------------------------------


class TestFourWindsSettings:
    """Verify has_suufon_renda toggle and four_winds_discard_count threshold."""

    def test_enabled_four_same_wind(self):
        """Four same wind discards triggers when enabled."""
        rs = MahjongRoundState(
            players=tuple(MahjongPlayer(seat=i, name=f"P{i}", score=25000) for i in range(4)),
            all_discards=tuple(TilesConverter.string_to_136_array(honors="1111")),
        )
        settings = GameSettings(has_suufon_renda=True)
        assert check_four_winds(rs, settings) is True

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

    def test_open_meld_blocks_four_winds(self):
        """Four same wind discards does not trigger if an open meld exists."""
        rs = MahjongRoundState(
            players=tuple(MahjongPlayer(seat=i, name=f"P{i}", score=25000) for i in range(4)),
            all_discards=tuple(TilesConverter.string_to_136_array(honors="1111")),
            players_with_open_hands=(1,),
        )
        settings = GameSettings()
        assert check_four_winds(rs, settings) is False


# ---------------------------------------------------------------------------
# Four Riichi (Suucha Riichi)
# ---------------------------------------------------------------------------


class TestFourRiichiSettings:
    """Verify has_suucha_riichi toggle."""

    def _round_state_with_riichi(self, riichi_seats):
        """Round state with specific players in riichi."""
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"P{i}",
                is_riichi=(i in riichi_seats),
                score=25000,
            )
            for i in range(4)
        )
        return MahjongRoundState(players=players)

    def test_all_four_riichi_triggers(self):
        """Four riichi triggers when all players are in riichi."""
        rs = self._round_state_with_riichi({0, 1, 2, 3})
        settings = GameSettings(has_suucha_riichi=True)
        assert check_four_riichi(rs, settings) is True

    def test_three_riichi_does_not_trigger(self):
        """Three riichi does not trigger abortive draw."""
        rs = self._round_state_with_riichi({0, 1, 2})
        settings = GameSettings()
        assert check_four_riichi(rs, settings) is False

    def test_check_uses_num_players(self):
        """check_four_riichi compares against settings.num_players, not hardcoded 4."""
        rs = self._round_state_with_riichi({0, 1, 2, 3})
        settings = GameSettings()
        # All 4 in riichi, num_players=4, so riichi_count == num_players
        assert check_four_riichi(rs, settings) is True

    def test_default_setting_is_enabled(self):
        """Default has_suucha_riichi is True."""
        assert GameSettings().has_suucha_riichi is True


# ---------------------------------------------------------------------------
# Triple Ron
# ---------------------------------------------------------------------------


class TestTripleRonSettings:
    """Verify has_triple_ron_abort toggle and triple_ron_count threshold."""

    def test_three_ron_callers_triggers(self):
        """Three ron callers triggers abortive draw with default settings."""
        assert check_triple_ron([0, 1, 2], 3) is True

    def test_two_ron_callers_no_trigger(self):
        """Two ron callers does not trigger (double ron allowed)."""
        assert check_triple_ron([0, 2], 3) is False

    def test_custom_triple_ron_count(self):
        """With triple_ron_count=2, two callers triggers abortive draw."""
        assert check_triple_ron([0, 2], 2) is True


# ---------------------------------------------------------------------------
# Process Abortive Draw
# ---------------------------------------------------------------------------


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
