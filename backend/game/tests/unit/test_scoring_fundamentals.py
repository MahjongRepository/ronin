"""
Verifies honba bonuses, payment rounding, noten penalty, keishiki tenpai,
goshashonyu rounding, and tie-breaking rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mahjong.tile import TilesConverter

from game.logic.game import calculate_final_scores, finalize_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import is_tempai, process_exhaustive_draw
from game.logic.scoring import (
    HandResult,
    ScoringContext,
    apply_double_ron_score,
    apply_ron_score,
    apply_tsumo_score,
    calculate_hand_value,
)
from game.logic.settings import GameSettings, validate_settings
from game.logic.state import Discard
from game.logic.types import YakuInfo
from game.logic.wall import Wall
from game.tests.conftest import create_game_state, create_player, create_round_state

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    return [YakuInfo(yaku_id=yid, han=0) for yid in yaku_ids]


def _scoring_game_state(
    *,
    honba: int = 0,
    riichi: int = 0,
    dealer_seat: int = 0,
    settings: GameSettings | None = None,
) -> MahjongGameState:
    players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
    round_state = create_round_state(players=players, dealer_seat=dealer_seat)
    return create_game_state(
        round_state=round_state,
        honba_sticks=honba,
        riichi_sticks=riichi,
        settings=settings,
    )


# ============================================================================
# Honba configurable bonus
# ============================================================================


class TestHonbaRonBonus:
    """Verify honba ron bonus uses settings.honba_ron_bonus, not hardcoded 300."""

    def test_custom_honba_ron_bonus(self):
        """Custom honba_ron_bonus=500 with 2 honba adds 1000 (not 600)."""
        settings = GameSettings(honba_ron_bonus=500)
        game_state = _scoring_game_state(honba=2, settings=settings)
        hand_result = HandResult(han=2, fu=30, cost_main=2000, yaku=_yaku(0))

        new_rs, _, _ = apply_ron_score(game_state, winner_seat=1, loser_seat=2, hand_result=hand_result, winning_tile=0)

        # 2000 base + 2*500 honba = 3000
        assert new_rs.players[1].score == 25000 + 3000
        assert new_rs.players[2].score == 25000 - 3000

    def test_double_ron_each_winner_gets_honba(self):
        """In double ron, each winner independently receives the honba bonus."""
        game_state = _scoring_game_state(honba=3)
        hr1 = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))
        hr2 = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        new_rs, _, _ = apply_double_ron_score(game_state, winners=[(0, hr1), (2, hr2)], loser_seat=1, winning_tile=0)

        # each winner: 1000 + 3*300 = 1900
        assert new_rs.players[0].score == 25000 + 1900
        assert new_rs.players[2].score == 25000 + 1900
        # loser pays 1900 * 2 = 3800
        assert new_rs.players[1].score == 25000 - 3800


class TestHonbaTsumoBonus:
    """Verify honba tsumo bonus uses settings.honba_tsumo_bonus_per_loser, not hardcoded 100."""

    def test_custom_honba_tsumo_bonus(self):
        """Custom honba_tsumo_bonus_per_loser=200 with 1 honba adds 200 per loser."""
        settings = GameSettings(honba_tsumo_bonus_per_loser=200)
        game_state = _scoring_game_state(honba=1, settings=settings)
        # non-dealer tsumo: dealer pays 1000, non-dealers pay 500
        hand_result = HandResult(han=1, fu=30, cost_main=1000, cost_additional=500, yaku=_yaku(0))

        new_rs, _, _ = apply_tsumo_score(game_state, winner_seat=1, hand_result=hand_result)

        # dealer pays 1000+200=1200, non-dealers pay 500+200=700
        assert new_rs.players[0].score == 25000 - 1200
        assert new_rs.players[2].score == 25000 - 700
        assert new_rs.players[3].score == 25000 - 700
        # winner gets 1200+700+700=2600
        assert new_rs.players[1].score == 25000 + 2600


# ============================================================================
# Payment rounding UP to nearest 100 (fundamental, in library)
# ============================================================================


class TestPaymentRoundingUp:
    """Verify the mahjong library rounds individual payments UP to nearest 100."""

    def test_non_dealer_tsumo_costs_rounded_up(self):
        """Non-dealer tsumo: base points that aren't multiples of 100 get rounded UP."""
        # hand: 123m 456m 789m 123p 55p, win tile=5p (tanki)
        # menzen tsumo (1 han) + ittsu (2 han) = 3 han, 30 fu
        # base = 30 * 2^5 = 960 (not a multiple of 100)
        # non-dealer: dealer pays 2*960=1920→2000, non-dealer pays 960→1000
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="12355")
        dummy_discards = TilesConverter.string_to_136_array(man="1112")
        dora_indicators = TilesConverter.string_to_136_array(sou="6")
        dummy_discard = (Discard(tile_id=0),)
        players = tuple(
            create_player(seat=i, tiles=tuple(tiles) if i == 0 else None, discards=dummy_discard) for i in range(4)
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=1,  # seat 0 is non-dealer
            dora_indicators=dora_indicators,
            wall=tuple(range(70)),
            all_discards=dummy_discards,
        )
        game_state = create_game_state(round_state=round_state)
        player = game_state.round_state.players[0]

        settings = GameSettings(has_akadora=False)
        ctx = ScoringContext(player=player, round_state=game_state.round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, tiles[-1])

        assert result.error is None
        # 1920 → 2000, 960 → 1000 (ceiling to nearest 100)
        assert result.cost_main == 2000
        assert result.cost_additional == 1000
        assert result.cost_main % 100 == 0
        assert result.cost_additional % 100 == 0


# ============================================================================
# Noten penalty (configurable via noten_penalty_total)
# ============================================================================


class TestNotenPenaltyConfigurable:
    """Verify noten penalty uses settings.noten_penalty_total."""

    def _exhaust_game_state(
        self,
        *,
        tempai_seats: list[int],
        settings: GameSettings | None = None,
    ) -> MahjongGameState:
        tempai_hand = tuple(TilesConverter.string_to_136_array(man="1123456788899"))
        non_tempai_hand = tuple(TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357"))
        players = tuple(
            create_player(
                seat=i,
                score=25000,
                tiles=tempai_hand if i in tempai_seats else non_tempai_hand,
            )
            for i in range(4)
        )
        round_state = create_round_state(players=players, wall_obj=Wall())
        return create_game_state(round_state=round_state, settings=settings)

    def test_custom_noten_penalty_total(self):
        """Custom noten_penalty_total=6000: 1 tempai, 3 noten → each noten pays 2000."""
        settings = GameSettings(noten_penalty_total=6000)
        game_state = self._exhaust_game_state(tempai_seats=[0], settings=settings)

        new_rs, _, result = process_exhaustive_draw(game_state)

        assert result.score_changes[0] == 6000  # tempai receives 6000
        assert result.score_changes[1] == -2000
        assert result.score_changes[2] == -2000
        assert result.score_changes[3] == -2000
        assert new_rs.players[0].score == 31000

    def test_two_tempai_two_noten(self):
        """2 tempai, 2 noten: 3000 split → noten pays 1500, tempai gets 1500."""
        game_state = self._exhaust_game_state(tempai_seats=[0, 2])

        _new_rs, _, result = process_exhaustive_draw(game_state)

        assert result.score_changes[0] == 1500
        assert result.score_changes[1] == -1500
        assert result.score_changes[2] == 1500
        assert result.score_changes[3] == -1500

    def test_three_tempai_one_noten(self):
        """3 tempai, 1 noten: noten pays 3000, each tempai gets 1000."""
        game_state = self._exhaust_game_state(tempai_seats=[0, 1, 2])

        _new_rs, _, result = process_exhaustive_draw(game_state)

        assert result.score_changes[0] == 1000
        assert result.score_changes[1] == 1000
        assert result.score_changes[2] == 1000
        assert result.score_changes[3] == -3000

    def test_all_tempai_no_payment(self):
        """All 4 tempai: no payment."""
        game_state = self._exhaust_game_state(tempai_seats=[0, 1, 2, 3])

        _, _, result = process_exhaustive_draw(game_state)

        assert all(v == 0 for v in result.score_changes.values())

    def test_all_noten_no_payment(self):
        """All 4 noten: no payment."""
        game_state = self._exhaust_game_state(tempai_seats=[])

        _, _, result = process_exhaustive_draw(game_state)

        assert all(v == 0 for v in result.score_changes.values())


# ============================================================================
# Keishiki tenpai (fundamental)
# ============================================================================


class TestKeishikiTenpai:
    """Verify keishiki tenpai: structural tenpai counts even if waits are in others' hands."""

    def test_structural_tenpai_counts(self):
        """Keishiki tenpai: hand is structurally tenpai regardless of where wait tiles are."""
        # 123m 456m 789m 12p 55p = 13 tiles → waiting on 3p
        # is_tempai only checks structure + pure karaten, NOT external tile availability
        tiles = list(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        result = is_tempai(tiles, melds=())
        assert result is True

    def test_pure_karaten_with_all_copies_in_own_hand(self):
        """Pure karaten (all 4 copies of wait in own hand+melds) is NOT tenpai."""
        # closed: 123m 456m 789m 9p (10 tiles) + pon of 9p (3 tiles in meld) = 13
        # waiting on 9p, but all 4 copies are in hand(1) + pon(3)
        closed_tiles = list(TilesConverter.string_to_136_array(man="123456789", pin="9"))
        pon_tiles = TilesConverter.string_to_136_array(pin="999")
        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )
        result = is_tempai(closed_tiles, melds=(pon,))
        assert result is False

    def test_not_karaten_when_some_copies_elsewhere(self):
        """Holding 3 copies of wait tile (not all 4) is valid tenpai, not karaten."""
        # 111m 234m 567m 555p = 12 tiles... need 13.
        # 111m 234m 567m 555p 9s = 13 tiles → can form 111m 234m 567m + 555p(triplet) + 9s(tanki)
        # Waiting on 9s (tanki). Has 1 copy in hand, 3 elsewhere → not karaten → tenpai
        tiles = list(TilesConverter.string_to_136_array(man="111234567", pin="555", sou="9"))
        result = is_tempai(tiles, melds=())
        assert result is True


# ============================================================================
# Goshashonyu rounding (configurable via goshashonyu_threshold)
# ============================================================================


class TestGoshashonyuCustomThreshold:
    """Verify goshashonyu uses settings.goshashonyu_threshold."""

    def test_custom_threshold_400_rounds_500_up(self):
        """With threshold=400, a remainder of 500 rounds away from zero (not toward)."""
        settings = GameSettings(goshashonyu_threshold=400)
        # Player with 30500: diff from 30000 target = 500
        # With threshold=400: 500 > 400, so rounds up → +1
        raw = [(0, 30500), (1, 30000), (2, 20000), (3, 19500)]
        result = calculate_final_scores(raw, settings)

        # seat 0: (30500-30000)/1000 → remainder 500 > 400 → rounds to 1, +20 oka +20 uma = 41
        assert result[0][1] == 41
        # verify zero-sum
        assert sum(s for _, s in result) == 0

    def test_default_threshold_500_rounds_500_down(self):
        """With default threshold=500, remainder of 500 rounds toward zero."""
        settings = GameSettings()
        raw = [(0, 30500), (1, 30000), (2, 20000), (3, 19500)]
        result = calculate_final_scores(raw, settings)

        # seat 0: remainder 500 <= 500 → rounds to 0, +20 oka +20 uma = 40
        assert result[0][1] == 40
        assert sum(s for _, s in result) == 0


# ============================================================================
# Tie-breaking (configurable via tie_break_by_seat_order)
# ============================================================================


class TestTieBreaking:
    """Verify tie-breaking by proximity to starting dealer."""

    def test_equal_scores_starting_dealer_ranks_first(self):
        """With equal scores, starting dealer (seat 0) ranks highest."""
        players = tuple(create_player(seat=i, score=25000) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(round_state)

        _, result = finalize_game(game_state)

        assert result.standings[0].seat == 0
        assert result.standings[1].seat == 1
        assert result.standings[2].seat == 2
        assert result.standings[3].seat == 3

    def test_equal_scores_non_zero_starting_dealer(self):
        """With starting_dealer_seat=2, seat 2 ranks highest on equal scores."""
        players = tuple(create_player(seat=i, score=25000) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(round_state)
        game_state = game_state.model_copy(update={"starting_dealer_seat": 2})

        _, result = finalize_game(game_state)

        # proximity to seat 2: seat2=0, seat3=1, seat0=2, seat1=3
        assert result.standings[0].seat == 2
        assert result.standings[1].seat == 3
        assert result.standings[2].seat == 0
        assert result.standings[3].seat == 1

    def test_higher_score_always_beats_seat_proximity(self):
        """Score takes priority over seat proximity."""
        players = tuple(create_player(seat=i, score=score) for i, score in enumerate([24000, 26000, 25000, 25000]))
        round_state = create_round_state(players=players)
        game_state = create_game_state(round_state)

        _, result = finalize_game(game_state)

        assert result.standings[0].seat == 1  # 26000
        assert result.standings[1].seat == 2  # 25000 (closer to dealer 0 than seat 3)
        assert result.standings[2].seat == 3  # 25000
        assert result.standings[3].seat == 0  # 24000

    def test_double_ron_riichi_sticks_to_closest_counter_clockwise(self):
        """Double ron: riichi sticks go to winner closest counter-clockwise to discarder."""
        game_state = _scoring_game_state(riichi=2)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        # loser=0, winners=1,3. Counter-clockwise from 0: check 1,2,3 → seat 1 is first
        _, _, result = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )

        for w in result.winners:
            if w.winner_seat == 1:
                assert w.riichi_sticks_collected == 2
            else:
                assert w.riichi_sticks_collected == 0

    def test_tie_break_setting_false_rejected(self):
        """tie_break_by_seat_order=False is rejected by validation."""
        settings = GameSettings(tie_break_by_seat_order=False)
        with pytest.raises(Exception, match="tie_break_by_seat_order"):
            validate_settings(settings)
