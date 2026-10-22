from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mahjong.tile import TilesConverter

from game.logic.action_handlers import handle_ron
from game.logic.call_resolution import resolve_call_prompt
from game.logic.enums import (
    GameAction,
    MeldCallType,
    PromptKind,
    RoundPhase,
    RoundResultType,
)
from game.logic.events import RoundEndEvent
from game.logic.exceptions import InvalidDiscardError
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import call_chi, call_pon, can_call_chi, get_kuikae_tiles
from game.logic.round import discard_tile
from game.logic.scoring import (
    HandResult,
    apply_double_ron_score,
    apply_ron_score,
)
from game.logic.settings import GameSettings
from game.logic.state import Caller, CallResponse, PendingCallPrompt
from game.logic.state_utils import update_player
from game.logic.tiles import tile_to_34
from game.logic.turn import process_meld_call
from game.logic.types import MeldCallInput, SeatConfig, YakuInfo
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


def _create_double_ron_game_state(
    *,
    has_double_ron: bool = True,
    honba: int = 0,
    riichi: int = 0,
) -> tuple:
    settings = GameSettings(has_double_ron=has_double_ron)
    waiting_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1112"))
    win_tile = TilesConverter.string_to_136_array(pin="22")[1]

    game_state = init_game(_seat_configs(), seed="a" * 192, settings=settings, wall=list(range(136)))
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
    def test_double_ron__when_enabled__should_produce_double_ron_result(self):
        game_state, win_tile = _create_double_ron_game_state(has_double_ron=True)
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, can_ron=True)),
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
    def test_head_bump__when_double_ron_disabled__should_produce_single_ron(self):
        game_state, win_tile = _create_double_ron_game_state(has_double_ron=False)
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, can_ron=True)),
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

    def test_head_bump__when_double_ron_disabled__should_pick_closest_counter_clockwise_winner(self):
        game_state, win_tile = _create_double_ron_game_state(has_double_ron=False)
        round_state = game_state.round_state

        # Discarder is seat 0. Counter-clockwise order: 1, 2, 3.
        # Seat 1 is closest to seat 0 counter-clockwise.
        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=win_tile,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(Caller(seat=1, can_ron=True), Caller(seat=2, can_ron=True)),
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

    def test_head_bump__when_chankan_robbed_by_two_seats__should_pick_closest_counter_clockwise_to_kan_caller(self):
        kan_tiles = TilesConverter.string_to_136_array(man="1111")
        pon_meld = FrozenMeld(meld_type=FrozenMeld.PON, tiles=tuple(kan_tiles[:3]), opened=True, who=2)
        robber_tiles = TilesConverter.string_to_136_array(man="2233445566778899", pin="445566", sou="5555")
        kan_caller_tiles = TilesConverter.string_to_136_array(sou="1236789", pin="999")
        players = (
            create_player(seat=0, tiles=tuple(robber_tiles[::2])),
            create_player(seat=1),
            create_player(seat=2, tiles=(kan_tiles[3], *kan_caller_tiles), melds=(pon_meld,)),
            create_player(seat=3, tiles=tuple(robber_tiles[1::2])),
        )
        dead_wall = tuple(TilesConverter.string_to_136_array(honors="11112222333344"))
        round_state = create_round_state(
            players=players,
            wall=tuple(TilesConverter.string_to_136_array(honors="5555")),
            dead_wall=dead_wall,
            dora_indicators=(dead_wall[2],),
            phase=RoundPhase.PLAYING,
            current_player_seat=2,
        )
        game_state = create_game_state(round_state, settings=GameSettings(has_double_ron=False))

        meld_input = MeldCallInput(caller_seat=2, call_type=MeldCallType.ADDED_KAN, tile_id=kan_tiles[3])
        round_state, game_state, _events = process_meld_call(round_state, game_state, meld_input=meld_input)
        first = handle_ron(round_state, game_state, seat=0)
        result = handle_ron(first.new_round_state, first.new_game_state, seat=3)

        round_ends = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_ends) == 1
        assert round_ends[0].result.type == RoundResultType.RON
        assert round_ends[0].result.winner_seat == 3


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
        _, _, result = apply_double_ron_score(
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
        _, _, result = apply_double_ron_score(
            game_state,
            winners=[(0, hr), (3, hr)],
            loser_seat=2,
            winning_tile=0,
        )
        assert {w.winner_seat: w.riichi_sticks_collected for w in result.winners} == {0: 0, 3: 2}

    def test_double_ron_riichi_sticks__should_add_stick_value_to_closer_winner_score(self):
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
    def test_double_ron_honba__should_pay_honba_bonus_to_both_winners(self):
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

        new_rs, _, _ = apply_double_ron_score(
            game_state,
            winners=[(1, hr), (3, hr)],
            loser_seat=0,
            winning_tile=0,
        )
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
    def test_double_ron_score_conservation__should_sum_score_changes_to_zero(self):
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

    def test_double_ron_score_conservation__when_riichi_sticks__should_add_sticks_to_pool(self):
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
