"""
Verifies game-end threshold check (configurable), dealer renchan override in West
(fundamental), and rotation through West-1 to West-4 (fundamental).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.game import _get_wind_for_unique_dealers, check_game_end, process_round_end
from game.logic.settings import EnchousenType, GameSettings, GameType
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.types import (
    ExhaustiveDrawResult,
    HandResultInfo,
    TenpaiHand,
    TsumoResult,
    YakuInfo,
)
from game.tests.conftest import create_game_state

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState


def _west_game_state(
    *,
    unique_dealers: int = 9,
    player_scores: list[int] | None = None,
    dealer_seat: int = 0,
    winning_score_threshold: int = 30000,
    enchousen: EnchousenType = EnchousenType.SUDDEN_DEATH,
    game_type: GameType = GameType.HANCHAN,
) -> MahjongGameState:
    scores = player_scores or [25000, 25000, 25000, 25000]
    players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
    round_state = MahjongRoundState(players=players, dealer_seat=dealer_seat, round_wind=2)
    settings = GameSettings(
        game_type=game_type,
        enchousen=enchousen,
        winning_score_threshold=winning_score_threshold,
    )
    return create_game_state(
        round_state=round_state,
        unique_dealers=unique_dealers,
        settings=settings,
    )


def _tsumo(winner_seat: int) -> TsumoResult:
    return TsumoResult(
        winner_seat=winner_seat,
        hand_result=HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)]),
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        riichi_sticks_collected=0,
        closed_tiles=[0, 1, 2, 3],
        melds=[],
        win_tile=3,
    )


def _exhaustive_draw(*, tempai_seats: list[int], noten_seats: list[int]) -> ExhaustiveDrawResult:
    return ExhaustiveDrawResult(
        tempai_seats=tempai_seats,
        noten_seats=noten_seats,
        tenpai_hands=[TenpaiHand(seat=s, closed_tiles=[], melds=[]) for s in tempai_seats],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
    )


# ============================================================================
# End condition: winning_score_threshold (configurable)
# ============================================================================


class TestWestRoundEndCondition:
    """Game ends in West when any player reaches winning_score_threshold."""

    def test_game_ends_when_player_reaches_threshold_in_west(self):
        """West-1: one player at 30000 → game ends."""
        gs = _west_game_state(unique_dealers=9, player_scores=[30000, 25000, 22000, 23000])
        assert check_game_end(gs) is True

    def test_game_continues_in_west_without_threshold(self):
        """West-1: no player at threshold → game continues."""
        gs = _west_game_state(unique_dealers=9, player_scores=[29000, 25000, 23000, 23000])
        assert check_game_end(gs) is False

    def test_game_ends_mid_west_when_threshold_reached(self):
        """West-3: player reaches threshold → game ends immediately."""
        gs = _west_game_state(unique_dealers=11, player_scores=[35000, 20000, 22000, 23000])
        assert check_game_end(gs) is True

    def test_custom_winning_score_threshold(self):
        """Custom threshold of 40000: player at 35000 does not trigger game end."""
        gs = _west_game_state(
            unique_dealers=9,
            player_scores=[35000, 20000, 22000, 23000],
            winning_score_threshold=40000,
        )
        assert check_game_end(gs) is False

    def test_custom_threshold_reached(self):
        """Custom threshold of 40000: player at 40000 triggers game end."""
        gs = _west_game_state(
            unique_dealers=9,
            player_scores=[40000, 15000, 22000, 23000],
            winning_score_threshold=40000,
        )
        assert check_game_end(gs) is True

    def test_threshold_check_uses_gte(self):
        """Score exactly at threshold triggers game end (>= not >)."""
        gs = _west_game_state(unique_dealers=9, player_scores=[30000, 25000, 22000, 23000])
        assert check_game_end(gs) is True

    def test_threshold_not_checked_during_primary_wind(self):
        """During South round, having threshold score does not end game."""
        scores = [35000, 20000, 22000, 23000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.HANCHAN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=7, settings=settings)
        assert check_game_end(gs) is False


# ============================================================================
# Dealer renchan in West: applies but threshold overrides
# ============================================================================


class TestWestRoundRenchanOverride:
    """Renchan applies in West but game ends if any player has threshold."""

    def test_dealer_wins_with_threshold_game_ends(self):
        """Dealer wins in West-1 and a player has threshold → game ends."""
        gs = _west_game_state(
            unique_dealers=9,
            dealer_seat=0,
            player_scores=[30000, 24000, 23000, 23000],
        )
        # Dealer tsumo → renchan (unique_dealers stays 9)
        new_gs = process_round_end(gs, _tsumo(winner_seat=0))
        assert new_gs.unique_dealers == 9  # renchan
        assert new_gs.round_state.dealer_seat == 0  # dealer stays
        assert check_game_end(new_gs) is True  # but game ends due to threshold

    def test_dealer_wins_without_threshold_continues(self):
        """Dealer wins in West-1 but no player has threshold → game continues."""
        gs = _west_game_state(
            unique_dealers=9,
            dealer_seat=0,
            player_scores=[29000, 24000, 24000, 23000],
        )
        new_gs = process_round_end(gs, _tsumo(winner_seat=0))
        assert new_gs.unique_dealers == 9  # renchan
        assert new_gs.round_state.dealer_seat == 0
        assert check_game_end(new_gs) is False  # game continues

    def test_dealer_tenpai_draw_with_threshold_game_ends(self):
        """Dealer tenpai at exhaustive draw in West, threshold reached → game ends."""
        gs = _west_game_state(
            unique_dealers=10,
            dealer_seat=1,
            player_scores=[31000, 24000, 22000, 23000],
        )
        result = _exhaustive_draw(tempai_seats=[1], noten_seats=[0, 2, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.round_state.dealer_seat == 1  # dealer stays (tenpai renchan)
        assert check_game_end(new_gs) is True  # game ends due to threshold

    def test_dealer_tenpai_draw_without_threshold_continues(self):
        """Dealer tenpai at exhaustive draw in West, no threshold → continues."""
        gs = _west_game_state(
            unique_dealers=10,
            dealer_seat=1,
            player_scores=[29000, 24000, 24000, 23000],
        )
        result = _exhaustive_draw(tempai_seats=[1], noten_seats=[0, 2, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.round_state.dealer_seat == 1  # renchan
        assert check_game_end(new_gs) is False


# ============================================================================
# Rotation through West-1...West-4
# ============================================================================


class TestWestRoundRotation:
    """Rotation through West-1 to West-4; game ends after West-4 rotation."""

    def test_wind_is_west_for_unique_dealers_9_to_12(self):
        """unique_dealers 9-12 all map to wind 2 (West)."""
        settings = GameSettings()
        for ud in range(9, 13):
            assert _get_wind_for_unique_dealers(ud, settings) == 2

    def test_west_1_non_dealer_win_advances_to_west_2(self):
        """Non-dealer win at West-1 rotates to West-2."""
        gs = _west_game_state(unique_dealers=9, dealer_seat=0, player_scores=[25000, 25000, 25000, 25000])
        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.unique_dealers == 10
        assert new_gs.round_state.dealer_seat == 1
        assert new_gs.round_state.round_wind == 2  # still West

    def test_west_4_non_dealer_win_ends_game(self):
        """Non-dealer win at West-4 causes unique_dealers to reach 13 → game ends."""
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[25000, 25000, 25000, 25000])
        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.unique_dealers == 13
        assert check_game_end(new_gs) is True

    def test_west_4_dealer_noten_draw_ends_game(self):
        """Exhaustive draw at West-4 with dealer noten → rotation → game ends."""
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[25000, 25000, 25000, 25000])
        result = _exhaustive_draw(tempai_seats=[0], noten_seats=[1, 2, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.unique_dealers == 13
        assert check_game_end(new_gs) is True

    def test_west_4_renchan_continues_if_no_threshold(self):
        """Dealer wins at West-4 with no threshold reached → renchan, game continues."""
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[29000, 24000, 24000, 23000])
        new_gs = process_round_end(gs, _tsumo(winner_seat=3))
        assert new_gs.unique_dealers == 12  # renchan, not incremented
        assert new_gs.round_state.dealer_seat == 3
        assert check_game_end(new_gs) is False  # 12 > 12 is False

    def test_west_4_renchan_with_threshold_ends_game(self):
        """Dealer wins at West-4 and a player has threshold → game ends despite renchan."""
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[30000, 23000, 24000, 23000])
        new_gs = process_round_end(gs, _tsumo(winner_seat=3))
        assert new_gs.unique_dealers == 12  # renchan
        assert check_game_end(new_gs) is True  # threshold reached


# ============================================================================
# Tonpusen sudden death: South round is the extension
# ============================================================================


class TestTonpusenSuddenDeath:
    """Tonpusen extends into South round (sudden death) instead of West."""

    def test_tonpusen_south_round_continues_without_threshold(self):
        scores = [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=6, settings=settings)
        assert check_game_end(gs) is False

    def test_tonpusen_south_round_ends_with_threshold(self):
        scores = [31000, 24000, 22000, 23000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=6, settings=settings)
        assert check_game_end(gs) is True

    def test_tonpusen_south_4_ends_regardless(self):
        """After South-4 in tonpusen, game ends even without threshold."""
        scores = [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=9, settings=settings)
        assert check_game_end(gs) is True
