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
        hand_result=HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)], points=1000),
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
        hand_result=HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)], points=1000),
        scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        riichi_sticks_collected=0,
        closed_tiles=[0, 1, 2],
        melds=[],
    )


def _double_ron(winner1: int, winner2: int, loser: int) -> DoubleRonResult:
    hr = HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)], points=1000)
    return DoubleRonResult(
        loser_seat=loser,
        winning_tile=0,
        winners=[
            DoubleRonWinner(
                winner_seat=winner1,
                hand_result=hr,
                score_changes={},
                riichi_sticks_collected=0,
                closed_tiles=[0],
                melds=[],
            ),
            DoubleRonWinner(
                winner_seat=winner2,
                hand_result=hr,
                score_changes={},
                riichi_sticks_collected=0,
                closed_tiles=[0],
                melds=[],
            ),
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
        score_changes={0: 0, 1: 0, 2: 0, 3: 0},
    )


# ============================================================================
# Renchan: dealer repeat conditions (configurable)
# ============================================================================


class TestRenchanDealerWin:
    def test_renchan__when_dealer_tsumo__should_keep_seat_and_add_honba(self):
        gs = _game_state(honba=0)

        honba, rotate = _get_honba_and_rotation(gs, _tsumo(winner_seat=0))
        assert honba == 1
        assert rotate is False

    def test_renchan__when_dealer_ron__should_keep_seat_and_add_honba(self):
        gs = _game_state(honba=0)

        honba, rotate = _get_honba_and_rotation(gs, _ron(winner_seat=0, loser_seat=1))
        assert honba == 1
        assert rotate is False

    def test_renchan__when_dealer_in_double_ron__should_keep_seat_and_add_honba(self):
        gs = _game_state(honba=2)
        result = _double_ron(winner1=0, winner2=2, loser=1)

        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 3
        assert rotate is False

    def test_renchan__when_dealer_win_renchan_disabled__should_rotate_and_reset_honba(self):
        settings = GameSettings(renchan_on_dealer_win=False)
        gs = _game_state(honba=3, settings=settings)

        honba, rotate = _get_honba_and_rotation(gs, _tsumo(winner_seat=0))
        assert honba == 0
        assert rotate is True


class TestRenchanDealerTenpaiDraw:
    def test_renchan__when_dealer_tenpai_draw__should_keep_seat_and_add_honba(self):
        gs = _game_state(honba=1)
        result = _exhaustive_draw(tempai_seats=[0, 1], noten_seats=[2, 3])

        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 2
        assert rotate is False

    def test_renchan__when_dealer_noten_draw__should_rotate_and_add_honba(self):
        gs = _game_state(honba=1)
        result = _exhaustive_draw(tempai_seats=[1], noten_seats=[0, 2, 3])

        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 2
        assert rotate is True

    def test_renchan__when_dealer_tenpai_renchan_disabled__should_rotate(self):
        settings = GameSettings(renchan_on_dealer_tenpai_draw=False)
        gs = _game_state(honba=0, settings=settings)
        result = _exhaustive_draw(tempai_seats=[0], noten_seats=[1, 2, 3])

        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 1
        assert rotate is True


class TestRenchanAbortiveDraw:
    def test_renchan__when_abortive_draw__should_keep_seat_and_add_honba(self):
        gs = _game_state(honba=0)

        honba, rotate = _get_honba_and_rotation(gs, _abortive())
        assert honba == 1
        assert rotate is False

    def test_renchan__when_abortive_renchan_disabled__should_rotate_and_reset_honba(self):
        settings = GameSettings(renchan_on_abortive_draw=False)
        gs = _game_state(honba=5, settings=settings)

        honba, rotate = _get_honba_and_rotation(gs, _abortive())
        assert honba == 0
        assert rotate is True


# ============================================================================
# Dealer rotation: fundamental (inverse of renchan)
# ============================================================================


class TestDealerRotation:
    def test_dealer_rotation__when_non_dealer_tsumo__should_rotate_and_reset_honba(self):
        gs = _game_state(honba=3)

        honba, rotate = _get_honba_and_rotation(gs, _tsumo(winner_seat=2))
        assert honba == 0
        assert rotate is True

    def test_dealer_rotation__when_non_dealer_ron__should_rotate_and_reset_honba(self):
        gs = _game_state(honba=1)

        honba, rotate = _get_honba_and_rotation(gs, _ron(winner_seat=1, loser_seat=3))
        assert honba == 0
        assert rotate is True

    def test_dealer_rotation__when_double_ron_without_dealer__should_rotate_and_reset_honba(self):
        gs = _game_state(honba=2)
        result = _double_ron(winner1=1, winner2=3, loser=2)

        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 0
        assert rotate is True

    def test_dealer_rotation__when_all_noten_draw__should_rotate_and_add_honba(self):
        gs = _game_state(honba=0)
        result = _exhaustive_draw(tempai_seats=[], noten_seats=[0, 1, 2, 3])

        honba, rotate = _get_honba_and_rotation(gs, result)
        assert honba == 1
        assert rotate is True

    def test_process_round_end__when_non_dealer_wins__should_advance_dealer_seat(self):
        gs = _game_state(dealer_seat=0, honba=0)

        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.round_state.dealer_seat == 1
        assert new_gs.unique_dealers == 2
        assert new_gs.honba_sticks == 0

    def test_process_round_end__when_dealer_is_seat_3__should_wrap_to_seat_0(self):
        rs = create_round_state(dealer_seat=3)
        gs = create_game_state(round_state=rs, honba_sticks=0)

        new_gs = process_round_end(gs, _tsumo(winner_seat=1))
        assert new_gs.round_state.dealer_seat == 0

    def test_process_round_end__when_dealer_wins__should_keep_dealer_seat(self):
        gs = _game_state(dealer_seat=0, honba=0)

        new_gs = process_round_end(gs, _tsumo(winner_seat=0))
        assert new_gs.round_state.dealer_seat == 0
        assert new_gs.unique_dealers == 1
        assert new_gs.honba_sticks == 1


# ============================================================================
# Nagashi mangan: honba counter for this result type
# ============================================================================


class TestNagashiManganHonba:
    def test_nagashi_mangan_honba__should_increment_honba(self):
        gs = _game_state(honba=3)
        result = _nagashi(tempai_seats=[0], noten_seats=[1, 2, 3])

        honba, _ = _get_honba_and_rotation(gs, result)
        assert honba == 4

    def test_nagashi_mangan_honba__when_dealer_noten__should_increment_honba(self):
        gs = _game_state(honba=0)
        result = _nagashi(tempai_seats=[1], noten_seats=[0, 2, 3])

        honba, _ = _get_honba_and_rotation(gs, result)
        assert honba == 1


# ============================================================================
# process_round_end integration: honba and dealer seat in full pipeline
# ============================================================================


class TestProcessRoundEndIntegration:
    def test_process_round_end__when_dealer_noten_draw__should_add_honba_and_rotate_dealer(self):
        gs = _game_state(dealer_seat=0, honba=1)
        result = _exhaustive_draw(tempai_seats=[1, 2], noten_seats=[0, 3])

        new_gs = process_round_end(gs, result)
        assert new_gs.honba_sticks == 2
        assert new_gs.round_state.dealer_seat == 1

    def test_process_round_end__when_nagashi_mangan__should_update_honba_and_dealer(self):
        gs = _game_state(dealer_seat=0, honba=2)
        result = _nagashi(tempai_seats=[0, 1], noten_seats=[2, 3])

        new_gs = process_round_end(gs, result)
        assert new_gs.honba_sticks == 3
        assert new_gs.round_state.dealer_seat == 0
