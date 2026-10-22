import pytest

from game.logic.call_resolution import complete_added_kan_after_chankan_decline
from game.logic.enums import RoundPhase
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
    HandResultInfo,
    NagashiManganResult,
    RonResult,
    SeatConfig,
    TenpaiHand,
    YakuInfo,
)
from game.tests.conftest import create_game_state, create_player, create_round_state

# shared tile tuples used by multiple helpers
_OTHER_HAND = (20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32)

# ============================================================================
# Settings Validation Tests
# ============================================================================


class TestValidateSettings:
    def test_validate_settings__when_renhou_baiman__should_raise(self):
        with pytest.raises(UnsupportedSettingsError, match="renhou_value=BAIMAN"):
            validate_settings(GameSettings(renhou_value=RenhouValue.BAIMAN))

    def test_validate_settings__when_tie_break_by_seat_order_false__should_raise_naming_it(self):
        with pytest.raises(UnsupportedSettingsError, match="tie_break_by_seat_order=False"):
            validate_settings(GameSettings(tie_break_by_seat_order=False))

    def test_validate_settings__when_several_unsupported_values__should_report_all(self):
        with pytest.raises(UnsupportedSettingsError, match=r"has_agariyame.*renhou_value=BAIMAN"):
            validate_settings(GameSettings(has_agariyame=True, renhou_value=RenhouValue.BAIMAN))

    def test_validate_settings__when_uma_valid__should_pass(self):
        validate_settings(GameSettings(uma=(30, 10, -10, -30)))

    def test_init_game__when_settings_unsupported__should_raise(self):
        configs = [SeatConfig(name=f"Player{i}") for i in range(4)]
        with pytest.raises(UnsupportedSettingsError, match="has_agariyame"):
            init_game(configs, seed="a" * 192, settings=GameSettings(has_agariyame=True))


# ============================================================================
# Renchan Behavior Tests
# ============================================================================


class TestRenchanNagashiMangan:
    def test_renchan__when_nagashi_mangan_and_dealer_tempai_and_renchan_enabled__should_keep_dealer_and_add_honba(self):
        settings = GameSettings(renchan_on_dealer_tenpai_draw=True)
        gs = create_game_state(honba_sticks=1, settings=settings)

        result = NagashiManganResult(
            qualifying_seats=[1],
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        # Nagashi mangan increments honba same as exhaustive draw (1 → 2)
        assert honba == 2
        assert should_rotate is False

    def test_renchan__when_nagashi_mangan_and_dealer_tempai_and_renchan_disabled__should_rotate_and_add_honba(self):
        settings = GameSettings(renchan_on_dealer_tenpai_draw=False)
        gs = create_game_state(honba_sticks=0, settings=settings)

        result = NagashiManganResult(
            qualifying_seats=[1],
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        # Nagashi mangan increments honba same as exhaustive draw (0 → 1)
        assert honba == 1
        assert should_rotate is True


class TestRenchanDealerRonDisabled:
    def test_renchan__when_dealer_wins_by_ron_and_renchan_on_win_disabled__should_rotate(self):
        settings = GameSettings(renchan_on_dealer_win=False)
        gs = create_game_state(honba_sticks=0, settings=settings)

        result = RonResult(
            winner_seat=0,
            loser_seat=1,
            winning_tile=0,
            hand_result=HandResultInfo(han=1, fu=30, yaku=[YakuInfo(yaku_id=0, han=1)]),
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
            riichi_sticks_collected=0,
            closed_tiles=[0, 1, 2],
            melds=[],
        )
        honba, should_rotate = _get_honba_and_rotation(gs, result)
        assert honba == 0
        assert should_rotate is True


# ============================================================================
# Game Type Tests
# ============================================================================


class TestGameTypeEnchousenExtensions:
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

    def test_check_game_end__when_tonpusen_east_complete_without_winner__should_continue(self):
        gs = self._game_state(unique_dealers=5, player_scores=[25000, 25000, 25000, 25000])
        assert check_game_end(gs) is False

    def test_check_game_end__when_tonpusen_south_complete__should_end(self):
        gs = self._game_state(unique_dealers=9)
        assert check_game_end(gs) is True

    def test_check_game_end__when_hanchan_south_complete_without_winner__should_continue(self):
        gs = self._game_state(
            unique_dealers=9,
            player_scores=[25000, 25000, 25000, 25000],
            game_type=GameType.HANCHAN,
        )
        assert check_game_end(gs) is False

    def test_check_game_end__when_hanchan_west_complete__should_end(self):
        gs = self._game_state(unique_dealers=13, game_type=GameType.HANCHAN)
        assert check_game_end(gs) is True


# ============================================================================
# Enchousen Tests
# ============================================================================


class TestEnchousenNone:
    def _game_state(
        self,
        unique_dealers: int = 1,
        enchousen: EnchousenType = EnchousenType.NONE,
        game_type: GameType = GameType.HANCHAN,
    ) -> MahjongGameState:
        scores = [25000, 25000, 25000, 25000]
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=scores[i]) for i in range(4))
        round_state = MahjongRoundState(players=players)
        settings = GameSettings(enchousen=enchousen, game_type=game_type)
        return MahjongGameState(
            round_state=round_state,
            unique_dealers=unique_dealers,
            settings=settings,
        )

    def test_check_game_end__when_enchousen_none_and_hanchan_south_complete__should_end(self):
        gs = self._game_state(unique_dealers=9, enchousen=EnchousenType.NONE)
        assert check_game_end(gs) is True

    def test_check_game_end__when_enchousen_none_and_tonpusen_east_complete__should_end(self):
        gs = self._game_state(
            unique_dealers=5,
            enchousen=EnchousenType.NONE,
            game_type=GameType.TONPUSEN,
        )
        assert check_game_end(gs) is True


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
    players.extend(create_player(seat=s, tiles=_OTHER_HAND, score=25000) for s in range(4) if s != caller_seat)
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
    def test_call_closed_kan__when_kandora_enabled__should_reveal_dora(self):
        rs, settings = _make_kan_test_round_state(has_kandora=True)
        new_rs, _meld = call_closed_kan(rs, seat=0, tile_id=0, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 2

    def test_call_closed_kan__when_kandora_disabled__should_not_reveal_or_defer_dora(self):
        rs, settings = _make_kan_test_round_state(has_kandora=False)
        new_rs, _meld = call_closed_kan(rs, seat=0, tile_id=0, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 1
        assert new_rs.wall.pending_dora_count == 0

    def test_call_open_kan__when_kandora_disabled__should_not_reveal_or_defer_dora(self):
        rs, settings = _make_open_kan_test_round_state(has_kandora=False)
        new_rs, _meld = call_open_kan(rs, caller_seat=1, discarder_seat=0, tile_id=0, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 1
        assert new_rs.wall.pending_dora_count == 0


class TestKandoraImmediateForClosedKan:
    def test_call_closed_kan__when_kandora_immediate__should_reveal_dora_at_once(self):
        rs, settings = _make_kan_test_round_state(kandora_immediate_for_closed_kan=True)
        new_rs, _meld = call_closed_kan(rs, seat=0, tile_id=0, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 2
        assert new_rs.wall.pending_dora_count == 0

    def test_call_closed_kan__when_kandora_not_immediate__should_defer_dora(self):
        rs, settings = _make_kan_test_round_state(kandora_immediate_for_closed_kan=False)
        new_rs, _meld = call_closed_kan(rs, seat=0, tile_id=0, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 1
        assert new_rs.wall.pending_dora_count == 1


class TestKandoraDeferredForOpenKan:
    def test_call_open_kan__when_kandora_deferred__should_defer_dora(self):
        rs, settings = _make_open_kan_test_round_state(kandora_deferred_for_open_kan=True)
        new_rs, _meld = call_open_kan(rs, caller_seat=1, discarder_seat=0, tile_id=0, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 1
        assert new_rs.wall.pending_dora_count == 1

    def test_call_open_kan__when_kandora_not_deferred__should_reveal_dora_at_once(self):
        rs, settings = _make_open_kan_test_round_state(kandora_deferred_for_open_kan=False)
        new_rs, _meld = call_open_kan(rs, caller_seat=1, discarder_seat=0, tile_id=0, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 2
        assert new_rs.wall.pending_dora_count == 0


class TestKandoraTimingAddedKan:
    def test_call_added_kan__when_kandora_deferred__should_defer_dora(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=True)
        new_rs, _meld = call_added_kan(rs, seat=0, tile_id=3, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 1
        assert new_rs.wall.pending_dora_count == 1

    def test_call_added_kan__when_kandora_not_deferred__should_reveal_dora_at_once(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=False)
        new_rs, _meld = call_added_kan(rs, seat=0, tile_id=3, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 2
        assert new_rs.wall.pending_dora_count == 0

    def test_call_added_kan__when_kandora_disabled__should_not_reveal_or_defer_dora(self):
        rs, settings = _make_pon_round_state(has_kandora=False)
        new_rs, _meld = call_added_kan(rs, seat=0, tile_id=3, settings=settings)
        assert len(new_rs.wall.dora_indicators) == 1
        assert new_rs.wall.pending_dora_count == 0


# ============================================================================
# Kan Dora Event Emission Tests (turn.py level)
# ============================================================================


class TestClosedKanDoraEvents:
    def test_process_closed_kan_call__when_kandora_immediate__should_emit_dora_revealed(self):
        rs, settings = _make_kan_test_round_state(kandora_immediate_for_closed_kan=True)
        gs = create_game_state(round_state=rs, settings=settings)

        _new_gs, events = _process_closed_kan_call(gs, caller_seat=0, tile_id=0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 1

    def test_process_closed_kan_call__when_kandora_not_immediate__should_not_emit_dora_revealed(self):
        rs, settings = _make_kan_test_round_state(kandora_immediate_for_closed_kan=False)
        gs = create_game_state(round_state=rs, settings=settings)

        _new_gs, events = _process_closed_kan_call(gs, caller_seat=0, tile_id=0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0


class TestOpenKanDoraEvents:
    def test_process_open_kan_call__when_kandora_deferred__should_not_emit_dora_revealed(self):
        rs, settings = _make_open_kan_test_round_state(kandora_deferred_for_open_kan=True)
        gs = create_game_state(round_state=rs, settings=settings)

        _new_gs, events = _process_open_kan_call(gs, caller_seat=1, discarder_seat=0, tile_id=0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0

    def test_process_open_kan_call__when_kandora_not_deferred__should_emit_dora_revealed(self):
        rs, settings = _make_open_kan_test_round_state(kandora_deferred_for_open_kan=False)
        gs = create_game_state(round_state=rs, settings=settings)

        _new_gs, events = _process_open_kan_call(gs, caller_seat=1, discarder_seat=0, tile_id=0)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 1


class TestAddedKanDoraEvents:
    def test_process_added_kan_call__when_kandora_deferred__should_not_emit_dora_revealed(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=True)
        gs = create_game_state(round_state=rs, settings=settings)

        _new_gs, events = _process_added_kan_call(gs, caller_seat=0, tile_id=3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0

    def test_process_added_kan_call__when_kandora_not_deferred__should_emit_dora_revealed(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=False)
        gs = create_game_state(round_state=rs, settings=settings)

        _new_gs, events = _process_added_kan_call(gs, caller_seat=0, tile_id=3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 1


# ============================================================================
# Chankan Decline Dora Emission Test (call_resolution.py)
# ============================================================================


class TestChankanDeclineDoraEvents:
    def test_complete_added_kan_after_chankan_decline__when_kandora_not_deferred__should_emit_dora_revealed(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=False)
        gs = create_game_state(round_state=rs, settings=settings)

        _new_gs, events = complete_added_kan_after_chankan_decline(gs, caller_seat=0, tile_id=3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 1

    def test_complete_added_kan_after_chankan_decline__when_kandora_deferred__should_not_emit_dora_revealed(self):
        rs, settings = _make_pon_round_state(kandora_deferred_for_open_kan=True)
        gs = create_game_state(round_state=rs, settings=settings)

        _new_gs, events = complete_added_kan_after_chankan_decline(gs, caller_seat=0, tile_id=3)
        dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
        assert len(dora_events) == 0
