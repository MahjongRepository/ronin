"""Tests for Phase 1: settings validation and wiring.

Covers:
- Settings validation (unsupported values fail fast)
- Renchan behavior settings
- game_type (tonpusen vs hanchan)
- enchousen (none vs sudden death)
- Kan dora timing settings
"""

import pytest

from game.logic.call_resolution import complete_added_kan_after_chankan_decline
from game.logic.enums import AbortiveDrawType, RoundPhase
from game.logic.events import DoraRevealedEvent
from game.logic.exceptions import UnsupportedSettingsError
from game.logic.game import (
    _get_honba_and_rotation,
    check_game_end,
    init_game,
)
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import call_added_kan, call_closed_kan, call_open_kan
from game.logic.settings import (
    EnchousenType,
    GameSettings,
    GameType,
    RenhouValue,
    validate_settings,
)
from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState
from game.logic.turn import _process_added_kan_call, _process_closed_kan_call, _process_open_kan_call
from game.logic.types import (
    AbortiveDrawResult,
    ExhaustiveDrawResult,
    HandResultInfo,
    NagashiManganResult,
    RonResult,
    SeatConfig,
    TsumoResult,
)
from game.tests.conftest import create_game_state, create_player, create_round_state

# shared tile tuples used by multiple helpers
_OTHER_HAND = (20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32)

# ============================================================================
# Settings Validation Tests
# ============================================================================


class TestValidateSettings:
    def test_default_settings_pass_validation(self):
        validate_settings(GameSettings())

    def test_num_players_not_four_raises(self):
        with pytest.raises(UnsupportedSettingsError, match="num_players=3"):
            validate_settings(GameSettings(num_players=3))

    def test_has_agariyame_true_raises(self):
        with pytest.raises(UnsupportedSettingsError, match="has_agariyame=True"):
            validate_settings(GameSettings(has_agariyame=True))

    def test_renhou_baiman_raises(self):
        with pytest.raises(UnsupportedSettingsError, match="renhou_value=BAIMAN"):
            validate_settings(GameSettings(renhou_value=RenhouValue.BAIMAN))

    def test_tie_break_by_seat_order_false_raises(self):
        with pytest.raises(UnsupportedSettingsError, match="tie_break_by_seat_order=False"):
            validate_settings(GameSettings(tie_break_by_seat_order=False))

    def test_multiple_unsupported_values_reports_all(self):
        with pytest.raises(UnsupportedSettingsError, match=r"num_players=3.*has_agariyame"):
            validate_settings(GameSettings(num_players=3, has_agariyame=True))

    def test_renhou_mangan_passes(self):
        validate_settings(GameSettings(renhou_value=RenhouValue.MANGAN))

    def test_renhou_yakuman_passes(self):
        validate_settings(GameSettings(renhou_value=RenhouValue.YAKUMAN))

    def test_renhou_none_passes(self):
        validate_settings(GameSettings(renhou_value=RenhouValue.NONE))

    def test_tonpusen_passes(self):
        validate_settings(GameSettings(game_type=GameType.TONPUSEN))

    def test_enchousen_none_passes(self):
        validate_settings(GameSettings(enchousen=EnchousenType.NONE))

    def test_init_game_validates_settings(self):
        configs = [SeatConfig(name=f"Player{i}") for i in range(4)]
        with pytest.raises(UnsupportedSettingsError, match="has_agariyame"):
            init_game(configs, settings=GameSettings(has_agariyame=True))


# ============================================================================
# Renchan Behavior Tests
# ============================================================================


class TestRenchanOnAbortiveDraw:
    def _game_state(self, *, renchan_on_abortive_draw: bool = True) -> MahjongGameState:
        settings = GameSettings(renchan_on_abortive_draw=renchan_on_abortive_draw)
        return create_game_state(honba_sticks=2, settings=settings)

    def test_default_abortive_draw_renchan(self):
        gs = self._game_state(renchan_on_abortive_draw=True)
        result = AbortiveDrawResult(reason=AbortiveDrawType.FOUR_WINDS)
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        assert honba == 3
        assert should_rotate is False

    def test_no_renchan_on_abortive_draw(self):
        gs = self._game_state(renchan_on_abortive_draw=False)
        result = AbortiveDrawResult(reason=AbortiveDrawType.FOUR_WINDS)
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        assert honba == 0
        assert should_rotate is True


class TestRenchanOnDealerTenpaiDraw:
    def _game_state(self, *, renchan_on_dealer_tenpai_draw: bool = True) -> MahjongGameState:
        settings = GameSettings(renchan_on_dealer_tenpai_draw=renchan_on_dealer_tenpai_draw)
        return create_game_state(honba_sticks=1, settings=settings)

    def test_default_dealer_tenpai_no_rotation(self):
        gs = self._game_state(renchan_on_dealer_tenpai_draw=True)
        result = ExhaustiveDrawResult(
            tempai_seats=[0], noten_seats=[1, 2, 3], score_changes={0: 0, 1: 0, 2: 0, 3: 0}
        )
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        assert honba == 2
        assert should_rotate is False

    def test_default_dealer_noten_rotates(self):
        gs = self._game_state(renchan_on_dealer_tenpai_draw=True)
        result = ExhaustiveDrawResult(
            tempai_seats=[1], noten_seats=[0, 2, 3], score_changes={0: 0, 1: 0, 2: 0, 3: 0}
        )
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        assert honba == 2
        assert should_rotate is True

    def test_no_renchan_dealer_tenpai_still_rotates(self):
        gs = self._game_state(renchan_on_dealer_tenpai_draw=False)
        result = ExhaustiveDrawResult(
            tempai_seats=[0], noten_seats=[1, 2, 3], score_changes={0: 0, 1: 0, 2: 0, 3: 0}
        )
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        assert honba == 2
        assert should_rotate is True

    def test_no_renchan_nagashi_mangan_dealer_tenpai_rotates(self):
        settings = GameSettings(renchan_on_dealer_tenpai_draw=False)
        gs = create_game_state(honba_sticks=0, settings=settings)
        result = NagashiManganResult(
            qualifying_seats=[1],
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        _honba, should_rotate = _get_honba_and_rotation(gs, result)
        assert should_rotate is True


class TestRenchanOnDealerWin:
    def _game_state(self, *, renchan_on_dealer_win: bool = True) -> MahjongGameState:
        settings = GameSettings(renchan_on_dealer_win=renchan_on_dealer_win)
        return create_game_state(honba_sticks=0, settings=settings)

    def _tsumo(self, winner_seat: int) -> TsumoResult:
        return TsumoResult(
            winner_seat=winner_seat,
            hand_result=HandResultInfo(han=1, fu=30, yaku=["Riichi"]),
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
            riichi_sticks_collected=0,
            closed_tiles=[0, 1, 2, 3],
            melds=[],
            win_tile=3,
        )

    def _ron(self, winner_seat: int, loser_seat: int) -> RonResult:
        return RonResult(
            winner_seat=winner_seat,
            loser_seat=loser_seat,
            winning_tile=0,
            hand_result=HandResultInfo(han=1, fu=30, yaku=["Riichi"]),
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
            riichi_sticks_collected=0,
            closed_tiles=[0, 1, 2],
            melds=[],
        )

    def test_default_dealer_win_renchan(self):
        gs = self._game_state(renchan_on_dealer_win=True)
        honba, should_rotate = _get_honba_and_rotation(gs, self._tsumo(winner_seat=0))
        assert honba == 1
        assert should_rotate is False

    def test_no_renchan_dealer_win_rotates(self):
        gs = self._game_state(renchan_on_dealer_win=False)
        honba, should_rotate = _get_honba_and_rotation(gs, self._tsumo(winner_seat=0))
        assert honba == 0
        assert should_rotate is True

    def test_no_renchan_dealer_ron_win_rotates(self):
        gs = self._game_state(renchan_on_dealer_win=False)
        honba, should_rotate = _get_honba_and_rotation(gs, self._ron(winner_seat=0, loser_seat=1))
        assert honba == 0
        assert should_rotate is True

    def test_non_dealer_win_always_rotates(self):
        gs = self._game_state(renchan_on_dealer_win=True)
        honba, should_rotate = _get_honba_and_rotation(gs, self._tsumo(winner_seat=2))
        assert honba == 0
        assert should_rotate is True


# ============================================================================
# Game Type (Tonpusen) Tests
# ============================================================================


class TestGameTypeTonpusen:
    def _game_state(
        self,
        unique_dealers: int = 1,
        player_scores: list[int] | None = None,
        game_type: GameType = GameType.TONPUSEN,
        enchousen: EnchousenType = EnchousenType.SUDDEN_DEATH,
    ) -> MahjongGameState:
        scores = player_scores or [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        round_state = MahjongRoundState(players=players)
        settings = GameSettings(game_type=game_type, enchousen=enchousen)
        return MahjongGameState(
            round_state=round_state,
            unique_dealers=unique_dealers,
            settings=settings,
        )

    def test_tonpusen_east_not_complete_continues(self):
        gs = self._game_state(unique_dealers=4, player_scores=[35000, 25000, 20000, 20000])
        assert check_game_end(gs) is False

    def test_tonpusen_east_complete_with_winner_ends(self):
        gs = self._game_state(unique_dealers=5, player_scores=[35000, 25000, 20000, 20000])
        assert check_game_end(gs) is True

    def test_tonpusen_east_complete_no_winner_continues_to_south(self):
        gs = self._game_state(unique_dealers=5, player_scores=[25000, 25000, 25000, 25000])
        assert check_game_end(gs) is False

    def test_tonpusen_south_complete_ends(self):
        gs = self._game_state(unique_dealers=9)
        assert check_game_end(gs) is True

    def test_hanchan_south_complete_with_winner_ends(self):
        gs = self._game_state(
            unique_dealers=9,
            player_scores=[35000, 25000, 20000, 20000],
            game_type=GameType.HANCHAN,
        )
        assert check_game_end(gs) is True

    def test_hanchan_south_complete_no_winner_continues_to_west(self):
        gs = self._game_state(
            unique_dealers=9,
            player_scores=[25000, 25000, 25000, 25000],
            game_type=GameType.HANCHAN,
        )
        assert check_game_end(gs) is False

    def test_hanchan_west_complete_ends(self):
        gs = self._game_state(unique_dealers=13, game_type=GameType.HANCHAN)
        assert check_game_end(gs) is True


# ============================================================================
# Enchousen Tests
# ============================================================================


class TestEnchousen:
    def _game_state(
        self,
        unique_dealers: int = 1,
        player_scores: list[int] | None = None,
        enchousen: EnchousenType = EnchousenType.SUDDEN_DEATH,
        game_type: GameType = GameType.HANCHAN,
    ) -> MahjongGameState:
        scores = player_scores or [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        round_state = MahjongRoundState(players=players)
        settings = GameSettings(enchousen=enchousen, game_type=game_type)
        return MahjongGameState(
            round_state=round_state,
            unique_dealers=unique_dealers,
            settings=settings,
        )

    def test_enchousen_none_hanchan_ends_after_south(self):
        gs = self._game_state(unique_dealers=9, enchousen=EnchousenType.NONE)
        assert check_game_end(gs) is True

    def test_enchousen_none_hanchan_ends_even_without_winner(self):
        gs = self._game_state(
            unique_dealers=9,
            player_scores=[25000, 25000, 25000, 25000],
            enchousen=EnchousenType.NONE,
        )
        assert check_game_end(gs) is True

    def test_enchousen_sudden_death_hanchan_continues_without_winner(self):
        gs = self._game_state(
            unique_dealers=9,
            player_scores=[25000, 25000, 25000, 25000],
            enchousen=EnchousenType.SUDDEN_DEATH,
        )
        assert check_game_end(gs) is False

    def test_enchousen_none_tonpusen_ends_after_east(self):
        gs = self._game_state(
            unique_dealers=5,
            enchousen=EnchousenType.NONE,
            game_type=GameType.TONPUSEN,
        )
        assert check_game_end(gs) is True

    def test_enchousen_sudden_death_tonpusen_continues_to_south(self):
        gs = self._game_state(
            unique_dealers=5,
            player_scores=[25000, 25000, 25000, 25000],
            enchousen=EnchousenType.SUDDEN_DEATH,
            game_type=GameType.TONPUSEN,
        )
        assert check_game_end(gs) is False


# ============================================================================
# Kan Dora Timing Tests (state-level in melds.py)
# ============================================================================


def _make_kan_test_round_state(
    caller_seat: int = 0,
    *,
    has_kandora: bool = True,
    kandora_immediate_for_closed_kan: bool = True,
    kandora_deferred_for_open_kan: bool = True,
) -> tuple[MahjongRoundState, GameSettings]:
    """Create a round state suitable for kan dora timing tests.

    Sets up a round with tiles for kan operations and a dead wall.
    Returns (round_state, settings).
    """
    settings = GameSettings(
        has_kandora=has_kandora,
        kandora_immediate_for_closed_kan=kandora_immediate_for_closed_kan,
        kandora_deferred_for_open_kan=kandora_deferred_for_open_kan,
    )
    # tile IDs: 0-3 are the same tile_34 (tile 0), 4-7 are tile_34=1
    # give caller 4 copies of tile type 0 (IDs 0,1,2,3) + extra tiles
    caller_tiles = (0, 1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)
    players = [
        create_player(seat=caller_seat, tiles=caller_tiles, score=25000),
    ]
    players.extend(
        create_player(seat=s, tiles=_OTHER_HAND, score=25000) for s in range(4) if s != caller_seat
    )
    players.sort(key=lambda p: p.seat)

    dead_wall = tuple(range(100, 114))
    dora_indicators = (dead_wall[2],)
    wall = tuple(range(50, 80))

    rs = create_round_state(
        players=players,
        wall=wall,
        dead_wall=dead_wall,
        dora_indicators=dora_indicators,
        dealer_seat=0,
        current_player_seat=caller_seat,
        phase=RoundPhase.PLAYING,
    )
    return rs, settings


def _make_open_kan_test_round_state(
    *,
    has_kandora: bool = True,
    kandora_deferred_for_open_kan: bool = True,
) -> tuple[MahjongRoundState, GameSettings]:
    """Create a round state where seat 1 can call open kan on tile 0.

    Seat 1 has 3 copies of tile_34=0 (tile IDs 1,2,3).
    Returns (round_state, settings).
    """
    settings = GameSettings(
        has_kandora=has_kandora,
        kandora_deferred_for_open_kan=kandora_deferred_for_open_kan,
    )
    caller_tiles = (1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)
    seat0_tiles = (0, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45)
    seat2_tiles = (46, 47, 48, 49, 60, 61, 62, 63, 64, 65, 66, 67, 68)
    seat3_tiles = (69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81)
    players = [
        create_player(seat=0, tiles=seat0_tiles, score=25000),
        create_player(seat=1, tiles=caller_tiles, score=25000),
        create_player(seat=2, tiles=seat2_tiles, score=25000),
        create_player(seat=3, tiles=seat3_tiles, score=25000),
    ]

    dead_wall = tuple(range(100, 114))
    dora_indicators = (dead_wall[2],)
    wall = tuple(range(82, 100))

    rs = create_round_state(
        players=players,
        wall=wall,
        dead_wall=dead_wall,
        dora_indicators=dora_indicators,
        dealer_seat=0,
        current_player_seat=0,
        phase=RoundPhase.PLAYING,
    )
    return rs, settings


def _make_pon_round_state(
    *,
    kandora_deferred_for_open_kan: bool = True,
    has_kandora: bool = True,
) -> tuple[MahjongRoundState, GameSettings]:
    """Create a round state where seat 0 has a pon and the 4th tile in hand.

    Returns (round_state, settings).
    """
    settings = GameSettings(
        has_kandora=has_kandora,
        kandora_deferred_for_open_kan=kandora_deferred_for_open_kan,
    )
    pon_meld = FrozenMeld(
        meld_type=FrozenMeld.PON,
        tiles=(0, 1, 2),
        opened=True,
        called_tile=2,
        who=0,
        from_who=1,
    )
    caller_tiles = (3, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19)
    players = [
        create_player(seat=0, tiles=caller_tiles, melds=[pon_meld], score=25000),
    ]
    players.extend(create_player(seat=s, tiles=_OTHER_HAND, score=25000) for s in range(1, 4))

    dead_wall = tuple(range(100, 114))
    dora_indicators = (dead_wall[2],)
    wall = tuple(range(50, 80))

    rs = create_round_state(
        players=players,
        wall=wall,
        dead_wall=dead_wall,
        dora_indicators=dora_indicators,
        dealer_seat=0,
        current_player_seat=0,
        phase=RoundPhase.PLAYING,
    )
    return rs, settings


class TestHasKandora:
    def test_closed_kan_with_kandora_reveals_dora(self):
        rs, settings = _make_kan_test_round_state(has_kandora=True)
        new_rs, _meld = call_closed_kan(rs, 0, 0, settings)
        assert len(new_rs.dora_indicators) == 2

    def test_closed_kan_without_kandora_no_dora(self):
        rs, settings = _make_kan_test_round_state(has_kandora=False)
        new_rs, _meld = call_closed_kan(rs, 0, 0, settings)
        assert len(new_rs.dora_indicators) == 1
        assert new_rs.pending_dora_count == 0

    def test_open_kan_without_kandora_no_pending_dora(self):
        rs, settings = _make_open_kan_test_round_state(has_kandora=False)
        new_rs, _meld = call_open_kan(rs, 1, 0, 0, settings)
        assert len(new_rs.dora_indicators) == 1
        assert new_rs.pending_dora_count == 0


class TestKandoraImmediateForClosedKan:
    def test_immediate_true_reveals_dora_immediately(self):
        rs, settings = _make_kan_test_round_state(kandora_immediate_for_closed_kan=True)
        new_rs, _meld = call_closed_kan(rs, 0, 0, settings)
        assert len(new_rs.dora_indicators) == 2
        assert new_rs.pending_dora_count == 0

    def test_immediate_false_defers_dora(self):
        rs, settings = _make_kan_test_round_state(kandora_immediate_for_closed_kan=False)
        new_rs, _meld = call_closed_kan(rs, 0, 0, settings)
        assert len(new_rs.dora_indicators) == 1
        assert new_rs.pending_dora_count == 1


class TestKandoraDeferredForOpenKan:
    def test_deferred_true_defers_dora(self):
        rs, settings = _make_open_kan_test_round_state(kandora_deferred_for_open_kan=True)
        new_rs, _meld = call_open_kan(rs, 1, 0, 0, settings)
        assert len(new_rs.dora_indicators) == 1
        assert new_rs.pending_dora_count == 1

    def test_deferred_false_reveals_immediately(self):
        rs, settings = _make_open_kan_test_round_state(kandora_deferred_for_open_kan=False)
        new_rs, _meld = call_open_kan(rs, 1, 0, 0, settings)
        assert len(new_rs.dora_indicators) == 2
        assert new_rs.pending_dora_count == 0


class TestKandoraTimingAddedKan:
    def test_added_kan_deferred_true(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=True)
        new_rs, _meld = call_added_kan(rs, 0, 3, settings)
        assert len(new_rs.dora_indicators) == 1
        assert new_rs.pending_dora_count == 1

    def test_added_kan_deferred_false_reveals_immediately(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=False)
        new_rs, _meld = call_added_kan(rs, 0, 3, settings)
        assert len(new_rs.dora_indicators) == 2
        assert new_rs.pending_dora_count == 0

    def test_added_kan_no_kandora(self):
        rs, settings = _make_pon_round_state(has_kandora=False)
        new_rs, _meld = call_added_kan(rs, 0, 3, settings)
        assert len(new_rs.dora_indicators) == 1
        assert new_rs.pending_dora_count == 0


# ============================================================================
# Kan Dora Event Emission Tests (turn.py level)
# ============================================================================


class TestClosedKanDoraEvents:
    def test_immediate_emits_dora_event(self):
        rs, settings = _make_kan_test_round_state(kandora_immediate_for_closed_kan=True)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = _process_closed_kan_call(rs, gs, 0, 0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 1

    def test_deferred_no_dora_event(self):
        rs, settings = _make_kan_test_round_state(kandora_immediate_for_closed_kan=False)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = _process_closed_kan_call(rs, gs, 0, 0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0

    def test_no_kandora_no_dora_event(self):
        rs, settings = _make_kan_test_round_state(has_kandora=False)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = _process_closed_kan_call(rs, gs, 0, 0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0


class TestOpenKanDoraEvents:
    def test_deferred_no_immediate_dora_event(self):
        rs, settings = _make_open_kan_test_round_state(kandora_deferred_for_open_kan=True)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = _process_open_kan_call(rs, gs, 1, 0, 0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0

    def test_immediate_emits_dora_event(self):
        rs, settings = _make_open_kan_test_round_state(kandora_deferred_for_open_kan=False)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = _process_open_kan_call(rs, gs, 1, 0, 0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 1

    def test_no_kandora_no_dora_event(self):
        rs, settings = _make_open_kan_test_round_state(has_kandora=False)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = _process_open_kan_call(rs, gs, 1, 0, 0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0


class TestAddedKanDoraEvents:
    def test_deferred_no_immediate_dora_event(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=True)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = _process_added_kan_call(rs, gs, 0, 3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0

    def test_immediate_emits_dora_event(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=False)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = _process_added_kan_call(rs, gs, 0, 3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 1

    def test_no_kandora_no_dora_event(self):
        rs, settings = _make_pon_round_state(has_kandora=False)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = _process_added_kan_call(rs, gs, 0, 3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0


# ============================================================================
# Chankan Decline Dora Emission Test (call_resolution.py)
# ============================================================================


class TestChankanDeclineDoraEvents:
    def test_chankan_decline_immediate_emits_dora_event(self):
        """When chankan is declined and dora is immediate, emit DoraRevealedEvent."""
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=False)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = complete_added_kan_after_chankan_decline(rs, gs, 0, 3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 1

    def test_chankan_decline_deferred_no_dora_event(self):
        """When chankan is declined and dora is deferred, no DoraRevealedEvent."""
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=True)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = complete_added_kan_after_chankan_decline(rs, gs, 0, 3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0

    def test_chankan_decline_no_kandora_no_dora_event(self):
        """When chankan is declined and has_kandora=False, no DoraRevealedEvent."""
        rs, settings = _make_pon_round_state(has_kandora=False)
        gs = create_game_state(round_state=rs, settings=settings)
        _new_rs, _new_gs, events = complete_added_kan_after_chankan_decline(rs, gs, 0, 3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0
