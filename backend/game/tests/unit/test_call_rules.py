from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_kan, handle_pass, handle_ron
from game.logic.enums import (
    KanType,
    MeldCallType,
    RoundResultType,
)
from game.logic.events import RoundEndEvent
from game.logic.exceptions import InvalidDiscardError
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import call_chi, call_pon, can_call_chi, get_kuikae_tiles
from game.logic.round import discard_tile
from game.logic.scoring import (
    HandResult,
    apply_double_ron_score,
    apply_ron_score,
)
from game.logic.settings import GameSettings
from game.logic.state import Caller, Discard
from game.logic.tiles import tile_to_34
from game.logic.turn import process_discard_phase
from game.logic.types import KanActionData, YakuInfo
from game.tests.conftest import create_dealt_game_state, create_game_state, create_player, create_round_state
from game.tests.helpers.hands import (
    PIN_3_TRIPLE_RON_CALLER_HANDS,
    PIN_3_TRIPLE_RON_DEALER_HAND,
    PIN_3_TRIPLE_RON_DISCARD,
    tile_copies,
)

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState

_PIN_TILES = TilesConverter.string_to_136_array(pin="456789123")


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    return [YakuInfo(yaku_id=yid, han=1) for yid in yaku_ids]


# ============================================================================
# Kuikae: Same-tile restriction
# ============================================================================


class TestKuikaeSameTileRestriction:
    def test_kuikae__when_pon__should_forbid_same_tile_type(self):
        settings = GameSettings(has_kuikae=True)
        man_tiles = TilesConverter.string_to_136_array(man="1115")
        player0_tiles = (man_tiles[0], man_tiles[1], *_PIN_TILES[:7])

        players = [
            create_player(seat=0, tiles=player0_tiles),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
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

    def test_kuikae__when_chi__should_forbid_called_tile_type(self):
        settings = GameSettings(has_kuikae=True, has_kuikae_suji=False)
        man_tiles = TilesConverter.string_to_136_array(man="234")
        player1_tiles = (man_tiles[1], man_tiles[2], *_PIN_TILES[:7])

        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
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

    def test_kuikae__when_discarding_forbidden_tile__should_raise(self):
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

        with pytest.raises(InvalidDiscardError, match="not a legal discard"):
            discard_tile(round_state, seat=0, tile_id=man_tiles[0])

    def test_kuikae__when_discarding_allowed_tile__should_succeed(self):
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
    def test_kuikae__when_disabled_and_pon__should_not_restrict_discard(self):
        settings = GameSettings(has_kuikae=False)
        man_tiles = TilesConverter.string_to_136_array(man="1115")
        player0_tiles = (man_tiles[0], man_tiles[1], *_PIN_TILES[:7])

        players = [
            create_player(seat=0, tiles=player0_tiles),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
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

    def test_kuikae__when_disabled_and_chi__should_not_restrict_discard(self):
        settings = GameSettings(has_kuikae=False)
        man_tiles = TilesConverter.string_to_136_array(man="234")
        player1_tiles = (man_tiles[1], man_tiles[2], *_PIN_TILES[:7])

        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
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
    def test_kuikae_suji__when_called_lowest_of_sequence__should_forbid_suji_tile(self):
        man_tiles = TilesConverter.string_to_136_array(man="456")
        called_34 = tile_to_34(man_tiles[0])  # 4m
        sequence_34 = [tile_to_34(man_tiles[1]), tile_to_34(man_tiles[2])]  # 5m, 6m

        forbidden = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_34, sequence_tiles_34=sequence_34
        )
        # 4m (called tile) and 7m (suji above 6m) should be forbidden
        assert called_34 in forbidden
        man_7m_34 = tile_to_34(TilesConverter.string_to_136_array(man="7")[0])
        assert man_7m_34 in forbidden

    def test_kuikae_suji__when_called_highest_of_sequence__should_forbid_suji_tile(self):
        man_tiles = TilesConverter.string_to_136_array(man="456")
        called_34 = tile_to_34(man_tiles[2])  # 6m
        sequence_34 = [tile_to_34(man_tiles[0]), tile_to_34(man_tiles[1])]  # 4m, 5m

        forbidden = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_34, sequence_tiles_34=sequence_34
        )
        # 6m (called tile) and 3m (suji below 4m) should be forbidden
        assert called_34 in forbidden
        man_3m_34 = tile_to_34(TilesConverter.string_to_136_array(man="3")[0])
        assert man_3m_34 in forbidden

    def test_kuikae_suji__when_called_middle_of_sequence__should_forbid_only_called_tile(self):
        man_tiles = TilesConverter.string_to_136_array(man="456")
        called_34 = tile_to_34(man_tiles[1])  # 5m
        sequence_34 = [tile_to_34(man_tiles[0]), tile_to_34(man_tiles[2])]  # 4m, 6m

        forbidden = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_34, sequence_tiles_34=sequence_34
        )
        # Only 5m should be forbidden (no suji for middle tile)
        assert forbidden == [called_34]

    def test_kuikae_suji__when_no_suji_tile_exists__should_forbid_only_called_tile(self):
        man_tiles = TilesConverter.string_to_136_array(man="789")
        called_34 = tile_to_34(man_tiles[0])  # 7m
        sequence_34 = [tile_to_34(man_tiles[1]), tile_to_34(man_tiles[2])]  # 8m, 9m

        forbidden = get_kuikae_tiles(
            call_type=MeldCallType.CHI, called_tile_34=called_34, sequence_tiles_34=sequence_34
        )
        # Only 7m should be forbidden (10m doesn't exist, no suji)
        assert forbidden == [called_34]

    def test_kuikae_suji__when_suji_disabled_and_chi__should_forbid_only_called_tile(self):
        settings = GameSettings(has_kuikae=True, has_kuikae_suji=False)
        man_tiles = TilesConverter.string_to_136_array(man="456")
        player1_tiles = (man_tiles[1], man_tiles[2], *_PIN_TILES[:7])

        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
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

    def test_kuikae_suji__when_suji_enabled_and_chi__should_forbid_called_and_suji_tiles(self):
        settings = GameSettings(has_kuikae=True, has_kuikae_suji=True)
        man_tiles = TilesConverter.string_to_136_array(man="456")
        player1_tiles = (man_tiles[1], man_tiles[2], *_PIN_TILES[:7])

        players = [
            create_player(seat=0),
            create_player(seat=1, tiles=player1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
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


class TestChiOfferLeavesLegalDiscard:
    @pytest.mark.parametrize(
        ("hand", "called", "settings"),
        [
            pytest.param("1234", "1", GameSettings(), id="three_melds_1234m_chi_1m_leaves_1m_4m"),
            pytest.param(
                "1123",
                "1",
                GameSettings(has_kuikae_suji=False),
                id="three_melds_1123m_chi_1m_without_suji_leaves_1m_1m",
            ),
            pytest.param("1223", "2", GameSettings(), id="three_melds_1223m_chi_middle_2m_leaves_2m_2m"),
            pytest.param("1112344", "1", GameSettings(), id="two_melds_1112344m_chi_1m_leaves_1m_1m_1m_4m_4m"),
        ],
    )
    def test_can_call_chi__when_every_remaining_tile_would_be_kuikae_restricted__should_not_offer(
        self, hand: str, called: str, settings: GameSettings
    ):
        caller = create_player(seat=1, tiles=TilesConverter.string_to_136_array(man=hand))
        called_tile = TilesConverter.string_to_136_array(man=called * 4)[3]

        options = can_call_chi(caller, discarded_tile=called_tile, discarder_seat=0, caller_seat=1, settings=settings)
        assert options == []

    def test_can_call_chi__when_a_remaining_tile_stays_discardable__should_offer(self):
        man_1, man_2, man_3, man_5 = TilesConverter.string_to_136_array(man="1235")
        caller = create_player(seat=1, tiles=(man_1, man_2, man_3, man_5))
        called_1m = TilesConverter.string_to_136_array(man="1111")[3]

        options = can_call_chi(
            caller, discarded_tile=called_1m, discarder_seat=0, caller_seat=1, settings=GameSettings()
        )
        assert options == [(man_2, man_3)]


class TestKuikaeClearedAfterDiscard:
    def test_kuikae__when_player_discards__should_clear_restriction(self):
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


class TestHeadBumpWhenDoubleRonDisabled:
    def test_head_bump__when_double_ron_disabled__should_pick_closest_counter_clockwise_winner(self):
        players = (
            create_player(seat=0, tiles=(*PIN_3_TRIPLE_RON_DEALER_HAND, PIN_3_TRIPLE_RON_DISCARD)),
            *(create_player(seat=seat, tiles=hand) for seat, hand in enumerate(PIN_3_TRIPLE_RON_CALLER_HANDS, start=1)),
        )
        game_state = create_dealt_game_state(players, settings=GameSettings(has_double_ron=False))
        prompted, _events = process_discard_phase(game_state, PIN_3_TRIPLE_RON_DISCARD)

        passed = handle_pass(prompted, seat=1)
        first = handle_ron(passed.state, seat=2)
        result = handle_ron(first.state, seat=3)
        round_ends = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert [(e.result.type, e.result.winner_seat) for e in round_ends] == [(RoundResultType.RON, 2)]

    def test_head_bump__when_chankan_robbed_by_two_seats__should_pick_closest_counter_clockwise_to_kan_caller(self):
        one_man = tuple(tile_copies(copy, man="1")[0] for copy in range(4))
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=one_man[:3],
            opened=True,
            called_tile=one_man[0],
            who=2,
            from_who=1,
        )
        players = (
            create_player(seat=0, tiles=tile_copies(0, man="23456789", pin="456", sou="55")),
            create_player(
                seat=1,
                tiles=(*tile_copies(0, honors="1234567"), *tile_copies(2, man="234567")),
                discards=(Discard(tile_id=one_man[0]),),
            ),
            create_player(
                seat=2,
                tiles=(one_man[3], *tile_copies(0, sou="1236789", pin="999")),
                melds=(pon_meld,),
            ),
            create_player(seat=3, tiles=(*tile_copies(1, man="23456789", pin="456"), *tile_copies(2, sou="55"))),
        )
        game_state = create_dealt_game_state(
            players,
            current_player_seat=2,
            settings=GameSettings(has_double_ron=False),
        )

        kan = handle_kan(game_state, seat=2, data=KanActionData(tile_id=one_man[3], kan_type=KanType.ADDED))
        prompt = kan.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.callers == (Caller(seat=3, can_ron=True), Caller(seat=0, can_ron=True))

        first = handle_ron(kan.state, seat=0)
        result = handle_ron(first.state, seat=3)
        round_ends = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert [(e.result.type, e.result.winner_seat) for e in round_ends] == [(RoundResultType.RON, 3)]


# ============================================================================
# Double Ron: Riichi sticks to closest counter-clockwise winner
# ============================================================================


def _scoring_game_state(*, honba: int = 0, riichi: int = 0) -> MahjongGameState:
    round_state = create_round_state(wall=list(range(10)))
    return create_game_state(round_state, honba_sticks=honba, riichi_sticks=riichi)


class TestDoubleRonRiichiStickDistribution:
    def test_double_ron_riichi_sticks__should_go_to_closer_winner(self):
        game_state = _scoring_game_state(riichi=3)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        # Loser seat 0, winners 1 and 3. CCW from 0: 1 is first.
        _, result = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )
        assert {w.winner_seat: w.riichi_sticks_collected for w in result.winners} == {1: 3, 3: 0}

    def test_double_ron_riichi_sticks__when_lower_seat_winner_is_farther__should_go_to_closer_winner(self):
        game_state = _scoring_game_state(riichi=2)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        # Loser seat 2, winners 0 and 3. CCW from 2: 3 is first.
        _, result = apply_double_ron_score(
            game_state,
            winners=[(0, hr), (3, hr)],
            loser_seat=2,
            winning_tile=0,
        )
        assert {w.winner_seat: w.riichi_sticks_collected for w in result.winners} == {0: 0, 3: 2}

    def test_double_ron_riichi_sticks__should_add_stick_value_to_closer_winner_score(self):
        game_state = _scoring_game_state(riichi=2)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        new_game_state, _ = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )
        new_rs = new_game_state.round_state
        # Seat 1 (riichi receiver): 25000 + 1000 (hand) + 2000 (riichi) = 28000
        assert new_rs.players[1].score == 25000 + 1000 + 2 * 1000
        # Seat 3 (non-receiver): 25000 + 1000 (hand only)
        assert new_rs.players[3].score == 25000 + 1000


# ============================================================================
# Double Ron: Both winners receive honba bonus separately
# ============================================================================


class TestDoubleRonHonbaBonus:
    def test_double_ron_honba__should_pay_honba_bonus_to_both_winners(self):
        game_state = _scoring_game_state(honba=3)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        new_game_state, _ = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )
        new_rs = new_game_state.round_state
        honba_bonus = 3 * 300  # 900 per winner
        # Each winner: 1000 + 900 = 1900
        assert new_rs.players[1].score == 25000 + 1000 + honba_bonus
        assert new_rs.players[3].score == 25000 + 1000 + honba_bonus
        # Loser pays both: -1900 * 2 = -3800
        assert new_rs.players[0].score == 25000 - 2 * (1000 + honba_bonus)

    def test_double_ron_honba__when_custom_honba_value__should_apply_it_to_both_winners(self):
        settings = GameSettings(honba_ron_bonus=500)
        round_state = create_round_state(wall=list(range(10)))
        game_state = create_game_state(
            round_state,
            honba_sticks=2,
            riichi_sticks=0,
            settings=settings,
        )
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        new_game_state, _ = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )
        new_rs = new_game_state.round_state
        honba_bonus = 2 * 500  # 1000 per winner with custom setting
        assert new_rs.players[1].score == 25000 + 1000 + honba_bonus
        assert new_rs.players[3].score == 25000 + 1000 + honba_bonus

    def test_double_ron_honba__when_head_bump__should_pay_honba_once(self):
        settings = GameSettings(has_double_ron=False)
        round_state = create_round_state(wall=list(range(10)))
        game_state = create_game_state(
            round_state,
            honba_sticks=3,
            riichi_sticks=0,
            settings=settings,
        )
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        new_game_state, _ = apply_ron_score(
            game_state,
            winner_seat=1,
            loser_seat=0,
            hand_result=hr,
            winning_tile=0,
        )
        new_rs = new_game_state.round_state
        honba_bonus = 3 * 300
        assert new_rs.players[1].score == 25000 + 1000 + honba_bonus
        assert new_rs.players[0].score == 25000 - 1000 - honba_bonus


# ============================================================================
# Double Ron: Score conservation
# ============================================================================


class TestDoubleRonScoreConservation:
    def test_double_ron_score_conservation__should_sum_score_changes_to_zero(self):
        game_state = _scoring_game_state(honba=2, riichi=0)
        hr1 = HandResult(han=2, fu=30, cost_main=2000, yaku=_yaku(0))
        hr2 = HandResult(han=3, fu=30, cost_main=3900, yaku=_yaku(0))

        _, result = apply_double_ron_score(
            game_state,
            winners=[(1, hr1), (3, hr2)],
            loser_seat=0,
            winning_tile=0,
        )
        total_change = sum(result.score_changes.values())
        assert total_change == 0

    def test_double_ron_score_conservation__when_riichi_sticks__should_add_sticks_to_pool(self):
        game_state = _scoring_game_state(honba=0, riichi=3)
        hr = HandResult(han=1, fu=30, cost_main=1000, yaku=_yaku(0))

        _, result = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )
        # Score changes include riichi sticks from table (3000 bonus to one player)
        total_change = sum(result.score_changes.values())
        assert total_change == 3 * 1000  # riichi sticks are added to the pool
