"""
Verifies kuikae (swap-calling) restrictions and multiple ron (double ron) rules,
including head bump fallback when double ron is disabled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mahjong.tile import TilesConverter

from game.logic.call_resolution import resolve_call_prompt
from game.logic.enums import (
    CallType,
    GameAction,
    MeldCallType,
    RoundResultType,
)
from game.logic.exceptions import InvalidDiscardError
from game.logic.game import init_game
from game.logic.melds import call_chi, call_pon, get_kuikae_tiles
from game.logic.round import discard_tile
from game.logic.scoring import (
    HandResult,
    apply_double_ron_score,
    apply_ron_score,
)
from game.logic.settings import GameSettings
from game.logic.state import CallResponse, PendingCallPrompt
from game.logic.state_utils import update_player
from game.logic.tiles import tile_to_34
from game.logic.types import SeatConfig, YakuInfo
from game.tests.conftest import create_game_state, create_player, create_round_state

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState

_PIN_TILES = TilesConverter.string_to_136_array(pin="456789123")


def _seat_configs() -> list[SeatConfig]:
    return [SeatConfig(name=f"P{i}") for i in range(4)]


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    return [YakuInfo(yaku_id=yid, han=1) for yid in yaku_ids]


# ============================================================================
# Kuikae: Same-tile restriction
# ============================================================================


class TestKuikaeSameTileRestriction:
    """Kuikae same-tile restriction: cannot discard the same tile type that was claimed."""

    def test_pon_forbids_same_tile_type(self):
        """After pon, discarding the same tile type is forbidden."""
        man_tiles = TilesConverter.string_to_136_array(man="1115")
        player0_tiles = (man_tiles[0], man_tiles[1], *_PIN_TILES[:7])
        players = [
            create_player(seat=0, tiles=player0_tiles),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        settings = GameSettings(has_kuikae=True)
        round_state = create_round_state(
            players=players,
            current_player_seat=0,
            wall=list(range(10)),
        )

        new_state, _meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=1,
            tile_id=man_tiles[2],
            settings=settings,
        )

        # 1m (tile_34=0) should be forbidden
        man_1m_34 = tile_to_34(man_tiles[0])
        assert man_1m_34 in new_state.players[0].kuikae_tiles

    def test_chi_forbids_called_tile_type(self):
        """After chi, discarding the called tile type is always forbidden."""
        man_tiles = TilesConverter.string_to_136_array(man="234")
        player1_tiles = (man_tiles[1], man_tiles[2], *_PIN_TILES[:7])
        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
        settings = GameSettings(has_kuikae=True, has_kuikae_suji=False)
        round_state = create_round_state(
            players=players,
            current_player_seat=0,
            wall=list(range(10)),
        )

        new_state, _meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        called_34 = tile_to_34(man_tiles[0])
        assert called_34 in new_state.players[1].kuikae_tiles

    def test_discard_forbidden_tile_raises(self):
        """Discarding a kuikae-forbidden tile raises InvalidDiscardError."""
        man_tiles = TilesConverter.string_to_136_array(man="115")
        player0_tiles = (man_tiles[0], man_tiles[2], *_PIN_TILES[:7])
        man_1m_34 = tile_to_34(man_tiles[0])
        players = [
            create_player(seat=0, tiles=player0_tiles, kuikae_tiles=[man_1m_34]),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(players=players, current_player_seat=0)

        with pytest.raises(InvalidDiscardError, match="forbidden by kuikae"):
            discard_tile(round_state, seat=0, tile_id=man_tiles[0])

    def test_discard_allowed_tile_succeeds(self):
        """Discarding a non-forbidden tile succeeds even with kuikae restrictions."""
        man_tiles = TilesConverter.string_to_136_array(man="15")
        player0_tiles = (man_tiles[0], man_tiles[1], *_PIN_TILES[:7])
        man_1m_34 = tile_to_34(man_tiles[0])
        players = [
            create_player(seat=0, tiles=player0_tiles, kuikae_tiles=[man_1m_34]),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(players=players, current_player_seat=0)

        _new_state, discard = discard_tile(round_state, seat=0, tile_id=man_tiles[1])
        assert discard.tile_id == man_tiles[1]


class TestKuikaeDisabledSetting:
    """When has_kuikae=False, no restrictions are set."""

    def test_pon_no_kuikae_when_disabled(self):
        """Pon sets no kuikae restrictions when setting is disabled."""
        man_tiles = TilesConverter.string_to_136_array(man="1115")
        player0_tiles = (man_tiles[0], man_tiles[1], *_PIN_TILES[:7])
        players = [
            create_player(seat=0, tiles=player0_tiles),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        settings = GameSettings(has_kuikae=False)
        round_state = create_round_state(
            players=players,
            current_player_seat=0,
            wall=list(range(10)),
        )

        new_state, _meld = call_pon(
            round_state,
            caller_seat=0,
            discarder_seat=1,
            tile_id=man_tiles[2],
            settings=settings,
        )

        assert new_state.players[0].kuikae_tiles == ()

    def test_chi_no_kuikae_when_disabled(self):
        """Chi sets no kuikae restrictions when setting is disabled."""
        man_tiles = TilesConverter.string_to_136_array(man="234")
        player1_tiles = (man_tiles[1], man_tiles[2], *_PIN_TILES[:7])
        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
        settings = GameSettings(has_kuikae=False)
        round_state = create_round_state(
            players=players,
            current_player_seat=0,
            wall=list(range(10)),
        )

        new_state, _meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        assert new_state.players[1].kuikae_tiles == ()


# ============================================================================
# Kuikae: Suji restriction
# ============================================================================


class TestKuikaeSujiRestriction:
    """Kuikae suji restriction: cannot discard the tile at the opposite end of a chi sequence."""

    def test_suji_tile_forbidden_when_called_lowest(self):
        """Calling chi with the lowest tile forbids the suji tile above the sequence.

        Example: chi 456m where 4m is called. Suji extends one step beyond 6m -> 7m forbidden.
        """
        man_tiles = TilesConverter.string_to_136_array(man="456")
        called_34 = tile_to_34(man_tiles[0])  # 4m
        sequence_34 = [tile_to_34(man_tiles[1]), tile_to_34(man_tiles[2])]  # 5m, 6m

        forbidden = get_kuikae_tiles(MeldCallType.CHI, called_34, sequence_34)

        # 4m (called tile) and 7m (suji above 6m) should be forbidden
        assert called_34 in forbidden
        man_7m_34 = tile_to_34(TilesConverter.string_to_136_array(man="7")[0])
        assert man_7m_34 in forbidden

    def test_suji_tile_forbidden_when_called_highest(self):
        """Calling chi with the highest tile forbids the suji tile below the sequence.

        Example: chi 456m where 6m is called. Suji extends one step below 4m -> 3m forbidden.
        """
        man_tiles = TilesConverter.string_to_136_array(man="456")
        called_34 = tile_to_34(man_tiles[2])  # 6m
        sequence_34 = [tile_to_34(man_tiles[0]), tile_to_34(man_tiles[1])]  # 4m, 5m

        forbidden = get_kuikae_tiles(MeldCallType.CHI, called_34, sequence_34)

        # 6m (called tile) and 3m (suji below 4m) should be forbidden
        assert called_34 in forbidden
        man_3m_34 = tile_to_34(TilesConverter.string_to_136_array(man="3")[0])
        assert man_3m_34 in forbidden

    def test_no_suji_when_called_middle(self):
        """Calling chi with the middle tile has no suji restriction (only called tile forbidden)."""
        man_tiles = TilesConverter.string_to_136_array(man="456")
        called_34 = tile_to_34(man_tiles[1])  # 5m
        sequence_34 = [tile_to_34(man_tiles[0]), tile_to_34(man_tiles[2])]  # 4m, 6m

        forbidden = get_kuikae_tiles(MeldCallType.CHI, called_34, sequence_34)

        # Only 5m should be forbidden (no suji for middle tile)
        assert forbidden == [called_34]

    def test_suji_blocked_at_suit_boundary(self):
        """Suji tile crossing suit boundary is not forbidden (stays within suit).

        Example: chi 789m where 7m is called. Suji would be 10m which doesn't exist.
        """
        man_tiles = TilesConverter.string_to_136_array(man="789")
        called_34 = tile_to_34(man_tiles[0])  # 7m
        sequence_34 = [tile_to_34(man_tiles[1]), tile_to_34(man_tiles[2])]  # 8m, 9m

        forbidden = get_kuikae_tiles(MeldCallType.CHI, called_34, sequence_34)

        # Only 7m should be forbidden (10m doesn't exist, no suji)
        assert forbidden == [called_34]

    def test_chi_with_suji_disabled_only_forbids_called_tile(self):
        """With has_kuikae_suji=False, chi only forbids the called tile type (no suji)."""
        man_tiles = TilesConverter.string_to_136_array(man="456")
        player1_tiles = (man_tiles[1], man_tiles[2], *_PIN_TILES[:7])
        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
        settings = GameSettings(has_kuikae=True, has_kuikae_suji=False)
        round_state = create_round_state(
            players=players,
            current_player_seat=0,
            wall=list(range(10)),
        )

        new_state, _meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        called_34 = tile_to_34(man_tiles[0])
        assert new_state.players[1].kuikae_tiles == (called_34,)

    def test_chi_with_suji_enabled_forbids_both(self):
        """With has_kuikae_suji=True, chi forbids both the called tile and suji tile."""
        man_tiles = TilesConverter.string_to_136_array(man="456")
        player1_tiles = (man_tiles[1], man_tiles[2], *_PIN_TILES[:7])
        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
        settings = GameSettings(has_kuikae=True, has_kuikae_suji=True)
        round_state = create_round_state(
            players=players,
            current_player_seat=0,
            wall=list(range(10)),
        )

        new_state, _meld = call_chi(
            round_state,
            caller_seat=1,
            discarder_seat=0,
            tile_id=man_tiles[0],
            sequence_tiles=(man_tiles[1], man_tiles[2]),
            settings=settings,
        )

        called_34 = tile_to_34(man_tiles[0])
        man_7m_34 = tile_to_34(TilesConverter.string_to_136_array(man="7")[0])
        kuikae = new_state.players[1].kuikae_tiles
        assert called_34 in kuikae
        assert man_7m_34 in kuikae


class TestKuikaeClearedAfterDiscard:
    """Kuikae restrictions are cleared after a valid discard."""

    def test_kuikae_cleared_on_discard(self):
        """After a valid discard, kuikae restrictions are cleared."""
        man_tiles = TilesConverter.string_to_136_array(man="15")
        player0_tiles = (man_tiles[0], man_tiles[1], *_PIN_TILES[:7])
        man_1m_34 = tile_to_34(man_tiles[0])
        players = [
            create_player(seat=0, tiles=player0_tiles, kuikae_tiles=[man_1m_34]),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(players=players, current_player_seat=0)

        new_state, _discard = discard_tile(round_state, seat=0, tile_id=man_tiles[1])
        assert new_state.players[0].kuikae_tiles == ()


# ============================================================================
# Double Ron: Settings and Atamahane (Head Bump) fallback
# ============================================================================


def _create_double_ron_game_state(
    *,
    has_double_ron: bool = True,
    honba: int = 0,
    riichi: int = 0,
) -> tuple:
    """Create a game state where seats 1 and 2 can ron on seat 0's discard."""
    settings = GameSettings(has_double_ron=has_double_ron)
    waiting_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
    win_tile = TilesConverter.string_to_136_array(pin="22")[1]

    game_state = init_game(_seat_configs(), settings=settings, wall=list(range(136)))
    round_state = game_state.round_state
    round_state = update_player(round_state, 1, tiles=waiting_tiles)
    round_state = update_player(round_state, 2, tiles=waiting_tiles)
    game_state = game_state.model_copy(
        update={
            "round_state": round_state,
            "honba_sticks": honba,
            "riichi_sticks": riichi,
        },
    )
    return game_state, win_tile


class TestDoubleRonEnabled:
    """Double ron: both players win when setting is enabled."""

    def test_double_ron_produces_two_winners(self):
        """With has_double_ron=True, two ron callers both win."""
        game_state, win_tile = _create_double_ron_game_state(has_double_ron=True)
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1, 2),
            responses=(
                CallResponse(seat=1, action=GameAction.CALL_RON),
                CallResponse(seat=2, action=GameAction.CALL_RON),
            ),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        round_end_events = [e for e in result.events if hasattr(e, "result")]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.DOUBLE_RON


class TestHeadBumpWhenDoubleRonDisabled:
    """Head bump (atama hane): only closest counter-clockwise player wins when double ron disabled."""

    def test_head_bump_single_winner(self):
        """With has_double_ron=False, only one ron caller wins (head bump)."""
        game_state, win_tile = _create_double_ron_game_state(has_double_ron=False)
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1, 2),
            responses=(
                CallResponse(seat=1, action=GameAction.CALL_RON),
                CallResponse(seat=2, action=GameAction.CALL_RON),
            ),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        round_end_events = [e for e in result.events if hasattr(e, "result")]
        assert len(round_end_events) == 1
        # Head bump: should be a single RON, not double
        assert round_end_events[0].result.type == RoundResultType.RON

    def test_head_bump_closest_counter_clockwise_wins(self):
        """Head bump picks the winner closest counter-clockwise to the discarder."""
        game_state, win_tile = _create_double_ron_game_state(has_double_ron=False)
        round_state = game_state.round_state

        # Discarder is seat 0. Counter-clockwise order: 1, 2, 3.
        # Seat 1 is closest to seat 0 counter-clockwise.
        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1, 2),
            responses=(
                CallResponse(seat=1, action=GameAction.CALL_RON),
                CallResponse(seat=2, action=GameAction.CALL_RON),
            ),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        round_end_events = [e for e in result.events if hasattr(e, "result")]
        ron_result = round_end_events[0].result
        assert ron_result.type == RoundResultType.RON
        # Seat 1 should be the winner (closest counter-clockwise to seat 0)
        assert ron_result.winner_seat == 1


# ============================================================================
# Double Ron: Riichi sticks to closest counter-clockwise winner
# ============================================================================


def _scoring_game_state(*, honba: int = 0, riichi: int = 0) -> MahjongGameState:
    round_state = create_round_state(wall=list(range(10)))
    return create_game_state(round_state, honba_sticks=honba, riichi_sticks=riichi)


class TestDoubleRonRiichiStickDistribution:
    """In double ron, riichi sticks go to the winner closest counter-clockwise to the discarder."""

    def test_riichi_sticks_to_closer_winner(self):
        """Winner at seat 1 (closer) gets riichi sticks, not seat 3."""
        game_state = _scoring_game_state(riichi=3)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        # Loser seat 0, winners 1 and 3. CCW from 0: 1 is first.
        _, _, result = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )

        for w in result.winners:
            if w.winner_seat == 1:
                assert w.riichi_sticks_collected == 3
            else:
                assert w.riichi_sticks_collected == 0

    def test_riichi_sticks_with_different_discarder(self):
        """With loser at seat 2, CCW order is 3, 0, 1. Seat 3 gets sticks."""
        game_state = _scoring_game_state(riichi=2)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        # Loser seat 2, winners 0 and 3. CCW from 2: 3 is first.
        _, _, result = apply_double_ron_score(
            game_state,
            winners=[(0, hr), (3, hr)],
            loser_seat=2,
            winning_tile=0,
        )

        for w in result.winners:
            if w.winner_seat == 3:
                assert w.riichi_sticks_collected == 2
            else:
                assert w.riichi_sticks_collected == 0

    def test_riichi_sticks_amount_applied_to_score(self):
        """The riichi receiver's score includes the full riichi bonus."""
        game_state = _scoring_game_state(riichi=2)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        new_rs, _, _ = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )

        # Seat 1 (riichi receiver): 25000 + 1000 (hand) + 2000 (riichi) = 28000
        assert new_rs.players[1].score == 25000 + 1000 + 2 * 1000
        # Seat 3 (non-receiver): 25000 + 1000 (hand only)
        assert new_rs.players[3].score == 25000 + 1000


# ============================================================================
# Double Ron: Both winners receive honba bonus separately
# ============================================================================


class TestDoubleRonHonbaBonus:
    """Each winner independently receives the full honba bonus from the discarder."""

    def test_both_winners_receive_honba(self):
        """Each winner gets honba bonus separately; discarder pays to each."""
        game_state = _scoring_game_state(honba=3)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        new_rs, _, _ = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )

        honba_bonus = 3 * 300  # 900 per winner
        # Each winner: 1000 + 900 = 1900
        assert new_rs.players[1].score == 25000 + 1000 + honba_bonus
        assert new_rs.players[3].score == 25000 + 1000 + honba_bonus
        # Loser pays both: -1900 * 2 = -3800
        assert new_rs.players[0].score == 25000 - 2 * (1000 + honba_bonus)

    def test_honba_bonus_with_custom_setting(self):
        """Custom honba_ron_bonus setting applies to double ron."""
        settings = GameSettings(honba_ron_bonus=500)
        round_state = create_round_state(wall=list(range(10)))
        game_state = create_game_state(
            round_state,
            honba_sticks=2,
            riichi_sticks=0,
            settings=settings,
        )
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        new_rs, _, _ = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )

        honba_bonus = 2 * 500  # 1000 per winner with custom setting
        assert new_rs.players[1].score == 25000 + 1000 + honba_bonus
        assert new_rs.players[3].score == 25000 + 1000 + honba_bonus

    def test_single_ron_with_head_bump_no_double_payment(self):
        """With head bump (double ron disabled), only one winner receives honba bonus."""
        settings = GameSettings(has_double_ron=False)
        round_state = create_round_state(wall=list(range(10)))
        game_state = create_game_state(
            round_state,
            honba_sticks=3,
            riichi_sticks=0,
            settings=settings,
        )
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        new_rs, _, _ = apply_ron_score(
            game_state,
            winner_seat=1,
            loser_seat=0,
            hand_result=hr,
            winning_tile=0,
        )

        honba_bonus = 3 * 300
        assert new_rs.players[1].score == 25000 + 1000 + honba_bonus
        assert new_rs.players[0].score == 25000 - 1000 - honba_bonus


# ============================================================================
# Double Ron: Score conservation
# ============================================================================


class TestDoubleRonScoreConservation:
    """The total score change across all players in a double ron sums to zero (plus riichi sticks)."""

    def test_total_score_changes_sum_to_zero(self):
        """Score changes in double ron are zero-sum (excluding riichi sticks from table)."""
        game_state = _scoring_game_state(honba=2, riichi=0)
        hr1 = HandResult(han=2, fu=30, cost_main=2000, yaku=_yaku(0))
        hr2 = HandResult(han=3, fu=30, cost_main=3900, yaku=_yaku(0))

        _, _, result = apply_double_ron_score(
            game_state,
            winners=[(1, hr1), (3, hr2)],
            loser_seat=0,
            winning_tile=0,
        )

        total_change = sum(result.score_changes.values())
        assert total_change == 0

    def test_total_score_changes_account_for_riichi(self):
        """With riichi sticks on table, total player score gain equals initial + riichi pool."""
        game_state = _scoring_game_state(honba=0, riichi=3)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        _, _, result = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )

        # Score changes include riichi sticks from table (3000 bonus to one player)
        total_change = sum(result.score_changes.values())
        assert total_change == 3 * 1000  # riichi sticks are added to the pool
