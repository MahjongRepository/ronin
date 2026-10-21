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
    def test_west_round_end__when_player_reaches_threshold__should_end_game(self):
        gs = _west_game_state(unique_dealers=9, player_scores=[30000, 25000, 22000, 23000])
        assert check_game_end(gs) is True

    def test_west_round_end__when_no_player_reaches_threshold__should_continue_game(self):
        gs = _west_game_state(unique_dealers=9, player_scores=[29000, 25000, 23000, 23000])
        assert check_game_end(gs) is False

    def test_west_round_end__when_threshold_reached_mid_west__should_end_game(self):
        gs = _west_game_state(unique_dealers=11, player_scores=[35000, 20000, 22000, 23000])
        assert check_game_end(gs) is True

    def test_west_round_end__when_custom_threshold_not_reached__should_continue_game(self):
        gs = _west_game_state(
            unique_dealers=9,
            player_scores=[35000, 20000, 22000, 23000],
            winning_score_threshold=40000,
        )
        assert check_game_end(gs) is False

    def test_west_round_end__when_custom_threshold_reached__should_end_game(self):
        gs = _west_game_state(
            unique_dealers=9,
            player_scores=[40000, 15000, 22000, 23000],
            winning_score_threshold=40000,
        )
        assert check_game_end(gs) is True

    def test_west_round_end__when_still_in_primary_wind__should_ignore_threshold(self):
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
    def test_west_renchan__when_dealer_wins_with_threshold_reached__should_end_game(self):
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

    def test_west_renchan__when_dealer_wins_without_threshold__should_continue_game(self):
        gs = _west_game_state(
            unique_dealers=9,
            dealer_seat=0,
            player_scores=[29000, 24000, 24000, 23000],
        )
        new_gs = process_round_end(gs, _tsumo(winner_seat=0))
        assert new_gs.unique_dealers == 9  # renchan
        assert new_gs.round_state.dealer_seat == 0
        assert check_game_end(new_gs) is False  # game continues

    def test_west_renchan__when_dealer_tenpai_draw_with_threshold_reached__should_end_game(self):
        gs = _west_game_state(
            unique_dealers=10,
            dealer_seat=1,
            player_scores=[31000, 24000, 22000, 23000],
        )

        result = _exhaustive_draw(tempai_seats=[1], noten_seats=[0, 2, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.round_state.dealer_seat == 1  # dealer stays (tenpai renchan)
        assert check_game_end(new_gs) is True  # game ends due to threshold

    def test_west_renchan__when_dealer_tenpai_draw_without_threshold__should_continue_game(self):
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
    def test_west_rotation__when_unique_dealers_9_to_12__should_use_west_wind(self):
        for ud in range(9, 13):
            assert _get_wind_for_unique_dealers(ud) == 2

    def test_west_rotation__when_non_dealer_wins_west_1__should_advance_to_west_2(self):
        gs = _west_game_state(unique_dealers=9, dealer_seat=0, player_scores=[25000, 25000, 25000, 25000])

        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.unique_dealers == 10
        assert new_gs.round_state.dealer_seat == 1
        assert new_gs.round_state.round_wind == 2  # still West

    def test_west_rotation__when_non_dealer_wins_west_4__should_end_game(self):
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[25000, 25000, 25000, 25000])

        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.unique_dealers == 13
        assert check_game_end(new_gs) is True

    def test_west_rotation__when_dealer_noten_draw_in_west_4__should_end_game(self):
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[25000, 25000, 25000, 25000])

        result = _exhaustive_draw(tempai_seats=[0], noten_seats=[1, 2, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.unique_dealers == 13
        assert check_game_end(new_gs) is True

    def test_west_rotation__when_dealer_wins_west_4_without_threshold__should_continue_game(self):
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[29000, 24000, 24000, 23000])

        new_gs = process_round_end(gs, _tsumo(winner_seat=3))
        assert new_gs.unique_dealers == 12  # renchan, not incremented
        assert new_gs.round_state.dealer_seat == 3
        assert check_game_end(new_gs) is False  # 12 > 12 is False

    def test_west_rotation__when_dealer_wins_west_4_with_threshold__should_end_game(self):
        gs = _west_game_state(unique_dealers=12, dealer_seat=3, player_scores=[30000, 23000, 24000, 23000])

        new_gs = process_round_end(gs, _tsumo(winner_seat=3))
        assert new_gs.unique_dealers == 12  # renchan
        assert check_game_end(new_gs) is True  # threshold reached


# ============================================================================
# Tonpusen sudden death: South round is the extension
# ============================================================================


class TestTonpusenSuddenDeath:
    def test_tonpusen_sudden_death__when_south_without_threshold__should_continue_game(self):
        scores = [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=6, settings=settings)

        assert check_game_end(gs) is False

    def test_tonpusen_sudden_death__when_south_with_threshold__should_end_game(self):
        scores = [31000, 24000, 22000, 23000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=6, settings=settings)

        assert check_game_end(gs) is True

    def test_tonpusen_sudden_death__when_past_south_4__should_end_game(self):
        scores = [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        rs = MahjongRoundState(players=players, round_wind=1)
        settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.SUDDEN_DEATH)
        gs = create_game_state(round_state=rs, unique_dealers=9, settings=settings)

        assert check_game_end(gs) is True
