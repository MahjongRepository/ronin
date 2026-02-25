"""
Verifies renchan conditions (configurable), dealer rotation on noten draw (fundamental),
and honba counter increment/reset logic (fundamental).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.enums import AbortiveDrawType
from game.logic.game import _get_honba_and_rotation, process_round_end
from game.logic.settings import GameSettings
from game.logic.types import (
    AbortiveDrawResult,
    DoubleRonResult,
    DoubleRonWinner,
    ExhaustiveDrawResult,
    HandResultInfo,
    NagashiManganResult,
    RonResult,
    TenpaiHand,
    TsumoResult,
    YakuInfo,
)
from game.tests.conftest import create_game_state, create_round_state

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState


def _game_state(
    *,
    dealer_seat: int = 0,
    honba: int = 0,
    settings: GameSettings | None = None,
) -> MahjongGameState:
    rs = create_round_state(dealer_seat=dealer_seat)
    return create_game_state(round_state=rs, honba_sticks=honba, settings=settings)


def _exhaustive_draw(*, tempai_seats: list[int], noten_seats: list[int]) -> ExhaustiveDrawResult:
    return ExhaustiveDrawResult(
        tempai_seats=tempai_seats,
        noten_seats=noten_seats,
        tenpai_hands=[TenpaiHand(seat=s, closed_tiles=[], melds=[]) for s in tempai_seats],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
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


def _ron(winner_seat: int, loser_seat: int) -> RonResult:
    return RonResult(
        winner_seat=winner_seat,
        loser_seat=loser_seat,
        winning_tile=0,
        hand_result=HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)]),
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        riichi_sticks_collected=0,
        closed_tiles=[0, 1, 2],
        melds=[],
    )


def _double_ron(winner1: int, winner2: int, loser: int) -> DoubleRonResult:
    hr = HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)])
    return DoubleRonResult(
        loser_seat=loser,
        winning_tile=0,
        winners=[
            DoubleRonWinner(winner_seat=winner1, hand_result=hr, riichi_sticks_collected=0, closed_tiles=[0], melds=[]),
            DoubleRonWinner(winner_seat=winner2, hand_result=hr, riichi_sticks_collected=0, closed_tiles=[0], melds=[]),
        ],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
    )


def _nagashi(*, tempai_seats: list[int], noten_seats: list[int]) -> NagashiManganResult:
    return NagashiManganResult(
        qualifying_seats=[1],
        tempai_seats=tempai_seats,
        noten_seats=noten_seats,
        tenpai_hands=[TenpaiHand(seat=s, closed_tiles=[], melds=[]) for s in tempai_seats],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
    )


def _abortive() -> AbortiveDrawResult:
    return AbortiveDrawResult(
        reason=AbortiveDrawType.FOUR_WINDS,
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
    )


# ============================================================================
# Renchan: dealer repeat conditions (configurable)
# ============================================================================


class TestRenchanDealerWin:
    """Dealer win triggers renchan; configurable via renchan_on_dealer_win."""

    def test_dealer_tsumo_keeps_seat(self):
        gs = _game_state(honba=0)
        honba, rotate = _get_honba_and_rotation(gs, _tsumo(winner_seat=0))
        assert honba == 1
        assert rotate is False

    def test_dealer_ron_keeps_seat(self):
        gs = _game_state(honba=0)
        honba, rotate = _get_honba_and_rotation(gs, _ron(winner_seat=0, loser_seat=1))
        assert honba == 1
        assert rotate is False

    def test_dealer_in_double_ron_keeps_seat(self):
        """If dealer wins in double ron, honba increments (renchan)."""
        gs = _game_state(honba=2)
        result = _double_ron(winner1=0, winner2=2, loser=1)
        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 3
        assert rotate is False

    def test_setting_disabled_dealer_win_rotates(self):
        settings = GameSettings(renchan_on_dealer_win=False)
        gs = _game_state(honba=3, settings=settings)
        honba, rotate = _get_honba_and_rotation(gs, _tsumo(winner_seat=0))
        assert honba == 0
        assert rotate is True


class TestRenchanDealerTenpaiDraw:
    """Dealer tenpai at exhaustive draw triggers renchan; configurable."""

    def test_dealer_tenpai_keeps_seat(self):
        gs = _game_state(honba=1)
        result = _exhaustive_draw(tempai_seats=[0, 1], noten_seats=[2, 3])
        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 2
        assert rotate is False

    def test_dealer_noten_rotates(self):
        gs = _game_state(honba=1)
        result = _exhaustive_draw(tempai_seats=[1], noten_seats=[0, 2, 3])
        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 2
        assert rotate is True

    def test_setting_disabled_dealer_tenpai_still_rotates(self):
        settings = GameSettings(renchan_on_dealer_tenpai_draw=False)
        gs = _game_state(honba=0, settings=settings)
        result = _exhaustive_draw(tempai_seats=[0], noten_seats=[1, 2, 3])
        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 1
        assert rotate is True


class TestRenchanAbortiveDraw:
    """Abortive draw triggers renchan; configurable."""

    def test_abortive_draw_keeps_seat(self):
        gs = _game_state(honba=0)
        honba, rotate = _get_honba_and_rotation(gs, _abortive())
        assert honba == 1
        assert rotate is False

    def test_setting_disabled_abortive_draw_rotates(self):
        settings = GameSettings(renchan_on_abortive_draw=False)
        gs = _game_state(honba=5, settings=settings)
        honba, rotate = _get_honba_and_rotation(gs, _abortive())
        assert honba == 0
        assert rotate is True


# ============================================================================
# Dealer rotation: fundamental (inverse of renchan)
# ============================================================================


class TestDealerRotation:
    """Dealer rotates when not among winners or noten at exhaustive draw."""

    def test_non_dealer_win_rotates(self):
        gs = _game_state(honba=3)
        honba, rotate = _get_honba_and_rotation(gs, _tsumo(winner_seat=2))
        assert honba == 0
        assert rotate is True

    def test_non_dealer_ron_rotates(self):
        gs = _game_state(honba=1)
        honba, rotate = _get_honba_and_rotation(gs, _ron(winner_seat=1, loser_seat=3))
        assert honba == 0
        assert rotate is True

    def test_double_ron_without_dealer_rotates(self):
        gs = _game_state(honba=2)
        result = _double_ron(winner1=1, winner2=3, loser=2)
        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 0
        assert rotate is True

    def test_all_noten_draw_rotates(self):
        gs = _game_state(honba=0)
        result = _exhaustive_draw(tempai_seats=[], noten_seats=[0, 1, 2, 3])
        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 1
        assert rotate is True

    def test_process_round_end_advances_dealer_seat(self):
        """process_round_end rotates dealer from seat 0 to seat 1."""
        gs = _game_state(dealer_seat=0, honba=0)
        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.round_state.dealer_seat == 1
        assert new_gs.unique_dealers == 2
        assert new_gs.honba_sticks == 0

    def test_process_round_end_wraps_dealer_seat(self):
        """Dealer wraps from seat 3 back to seat 0."""
        rs = create_round_state(dealer_seat=3)
        gs = create_game_state(round_state=rs, honba_sticks=0)
        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.round_state.dealer_seat == 0

    def test_process_round_end_dealer_stays_on_renchan(self):
        """Dealer stays at seat 0 on dealer win."""
        gs = _game_state(dealer_seat=0, honba=0)
        new_gs = process_round_end(gs, _tsumo(winner_seat=0))
        assert new_gs.round_state.dealer_seat == 0
        assert new_gs.unique_dealers == 1
        assert new_gs.honba_sticks == 1


# ============================================================================
# Nagashi mangan: honba counter for this result type
# ============================================================================


class TestNagashiManganHonba:
    """Honba behaviour for NagashiManganResult (other result types covered
    by renchan and dealer rotation tests above)."""

    def test_honba_increments_on_nagashi_mangan(self):
        """Nagashi mangan increments honba same as exhaustive draw."""
        gs = _game_state(honba=3)
        result = _nagashi(tempai_seats=[0], noten_seats=[1, 2, 3])
        honba, _ = _get_honba_and_rotation(gs, result)
        assert honba == 4

    def test_honba_increments_on_nagashi_mangan_dealer_noten(self):
        """Nagashi mangan with dealer noten still increments honba."""
        gs = _game_state(honba=0)
        result = _nagashi(tempai_seats=[1], noten_seats=[0, 2, 3])
        honba, _ = _get_honba_and_rotation(gs, result)
        assert honba == 1


# ============================================================================
# process_round_end integration: honba and dealer seat in full pipeline
# ============================================================================


class TestProcessRoundEndIntegration:
    def test_exhaustive_draw_honba_and_rotation(self):
        """Exhaustive draw with dealer noten: honba increments, dealer rotates."""
        gs = _game_state(dealer_seat=0, honba=1)
        result = _exhaustive_draw(tempai_seats=[1, 2], noten_seats=[0, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.honba_sticks == 2
        assert new_gs.round_state.dealer_seat == 1

    def test_nagashi_mangan_honba_and_rotation(self):
        """Nagashi mangan with dealer tenpai: honba increments, dealer stays."""
        gs = _game_state(dealer_seat=0, honba=2)
        result = _nagashi(tempai_seats=[0, 1], noten_seats=[2, 3])
        new_gs = process_round_end(gs, result)
        assert new_gs.honba_sticks == 3
        assert new_gs.round_state.dealer_seat == 0
