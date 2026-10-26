from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mahjong.tile import TilesConverter

from game.logic.game import calculate_final_scores, finalize_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import is_tempai, process_exhaustive_draw
from game.logic.settings import GameSettings, validate_settings
from game.logic.types import YakuInfo
from game.tests.conftest import create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.wall import make_wall

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    return [YakuInfo(yaku_id=yid, han=0) for yid in yaku_ids]


# ============================================================================
# Noten penalty (configurable via noten_penalty_total)
# ============================================================================


class TestNotenPenaltyConfigurable:
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
        round_state = create_round_state(players=players, wall_obj=make_wall())
        return create_game_state(round_state=round_state, settings=settings)

    def test_process_exhaustive_draw__when_custom_noten_penalty_total__should_split_it(self):
        settings = GameSettings(noten_penalty_total=6000)
        game_state = self._exhaust_game_state(tempai_seats=[0], settings=settings)

        new_game_state, result = process_exhaustive_draw(game_state)
        new_rs = new_game_state.round_state
        assert result.score_changes[0] == 6000  # tempai receives 6000
        assert result.score_changes[1] == -2000
        assert result.score_changes[2] == -2000
        assert result.score_changes[3] == -2000
        assert new_rs.players[0].score == 31000

    def test_process_exhaustive_draw__when_two_tempai_two_noten__should_transfer_1500_each(self):
        game_state = self._exhaust_game_state(tempai_seats=[0, 2])

        _, result = process_exhaustive_draw(game_state)
        assert result.score_changes[0] == 1500
        assert result.score_changes[1] == -1500
        assert result.score_changes[2] == 1500
        assert result.score_changes[3] == -1500

    def test_process_exhaustive_draw__when_three_tempai_one_noten__should_charge_noten_3000(self):
        game_state = self._exhaust_game_state(tempai_seats=[0, 1, 2])

        _, result = process_exhaustive_draw(game_state)
        assert result.score_changes[0] == 1000
        assert result.score_changes[1] == 1000
        assert result.score_changes[2] == 1000
        assert result.score_changes[3] == -3000

    def test_process_exhaustive_draw__when_all_tempai__should_not_transfer_points(self):
        game_state = self._exhaust_game_state(tempai_seats=[0, 1, 2, 3])

        _, result = process_exhaustive_draw(game_state)
        assert all(v == 0 for v in result.score_changes.values())

    def test_process_exhaustive_draw__when_all_noten__should_not_transfer_points(self):
        game_state = self._exhaust_game_state(tempai_seats=[])

        _, result = process_exhaustive_draw(game_state)
        assert all(v == 0 for v in result.score_changes.values())


# ============================================================================
# Keishiki tenpai (fundamental)
# ============================================================================


class TestKeishikiTenpai:
    def test_is_tempai__when_hand_structurally_tenpai__should_be_true(self):
        # 123m 456m 789m 12p 55p = 13 tiles → waiting on 3p
        # is_tempai only checks structure + pure karaten, NOT external tile availability
        tiles = list(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        result = is_tempai(tiles, melds=())
        assert result is True

    def test_is_tempai__when_all_copies_of_wait_in_own_hand__should_be_false(self):
        closed_tiles = [*tile_copies(0, man="123456789"), *tile_copies(3, pin="9")]
        pon_tiles = tile_copies(0, pin="999")
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

    def test_is_tempai__when_wait_tile_copies_remain_elsewhere__should_be_true(self):
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
    def test_calculate_final_scores__when_goshashonyu_threshold_400_and_remainder_500__should_round_up(self):
        settings = GameSettings(goshashonyu_threshold=400)
        # Player with 30500: diff from 30000 target = 500
        # With threshold=400: 500 > 400, so rounds up → +1
        raw = [(0, 30500), (1, 30000), (2, 20000), (3, 19500)]
        result = calculate_final_scores(raw, settings)
        # seat 0: (30500-30000)/1000 → remainder 500 > 400 → rounds to 1, +20 oka +20 uma = 41
        assert result[0][1] == 41
        # verify zero-sum
        assert sum(s for _, s in result) == 0

    def test_calculate_final_scores__when_default_threshold_and_remainder_500__should_round_down(self):
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
    def test_finalize_game__when_scores_equal__should_rank_by_seat_from_starting_dealer(self):
        players = tuple(create_player(seat=i, score=25000) for i in range(4))
        round_state = create_round_state(players=players)
        game_state = create_game_state(round_state)

        _, result = finalize_game(game_state)
        assert result.standings[0].seat == 0
        assert result.standings[1].seat == 1
        assert result.standings[2].seat == 2
        assert result.standings[3].seat == 3

    def test_finalize_game__when_scores_equal_and_dealer_seat_2__should_rank_from_seat_2(self):
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

    def test_finalize_game__when_scores_differ__should_rank_score_before_seat_proximity(self):
        players = tuple(create_player(seat=i, score=score) for i, score in enumerate([24000, 26000, 25000, 25000]))
        round_state = create_round_state(players=players)
        game_state = create_game_state(round_state)

        _, result = finalize_game(game_state)
        assert result.standings[0].seat == 1  # 26000
        assert result.standings[1].seat == 2  # 25000 (closer to dealer 0 than seat 3)
        assert result.standings[2].seat == 3  # 25000
        assert result.standings[3].seat == 0  # 24000

    def test_validate_settings__when_tie_break_by_seat_order_false__should_raise(self):
        settings = GameSettings(tie_break_by_seat_order=False)
        with pytest.raises(Exception, match="tie_break_by_seat_order"):
            validate_settings(settings)
