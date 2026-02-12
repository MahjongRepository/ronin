"""
Unit tests for Phase 2 validation gaps.

Tests verify that each validation gap identified in the analysis is properly
closed with early validation. Invalid data raises InvalidGameActionError;
race-condition timing errors remain as soft ErrorEvent.
"""

from unittest.mock import patch

import pytest
from mahjong.tile import TilesConverter

from game.logic.action_handlers import (
    _find_offending_seat_from_prompt,
    _resolve_call_prompt_safe,
    _validate_caller_action_matches_prompt,
    handle_chi,
    handle_discard,
    handle_kan,
    handle_kyuushu,
    handle_pass,
    handle_pon,
    handle_riichi,
    handle_ron,
    handle_tsumo,
)
from game.logic.action_result import ActionResult
from game.logic.bot import BotPlayer, BotStrategy
from game.logic.bot_controller import BotController
from game.logic.enums import (
    BotType,
    CallType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldCallType,
    RoundPhase,
)
from game.logic.events import ErrorEvent
from game.logic.exceptions import GameRuleError, InvalidGameActionError, InvalidMeldError
from game.logic.game import init_game
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import (
    call_added_kan,
    call_chi,
    call_closed_kan,
    call_open_kan,
)
from game.logic.round import draw_tile
from game.logic.settings import GameSettings
from game.logic.state import (
    CallResponse,
    Discard,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.types import (
    ChiActionData,
    DiscardActionData,
    KanActionData,
    MeldCaller,
    PonActionData,
    RiichiActionData,
    SeatConfig,
)
from game.tests.conftest import create_game_state, create_player, create_round_state


def _default_seat_configs():
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Bot1", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Bot2", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Bot3", bot_type=BotType.TSUMOGIRI),
    ]


def _create_frozen_game_state(seed=12345.0):
    game_state = init_game(_default_seat_configs(), seed=seed)
    new_round_state, _tile = draw_tile(game_state.round_state)
    return game_state.model_copy(update={"round_state": new_round_state})


class TestChiEarlyValidation:
    """Test chi sequence_tiles validation before recording response."""

    def _create_chi_state(self):
        """Create state with a pending meld prompt where seat 1 can chi."""
        # seat 0 discards 1m (tile 0), seat 1 is kamicha
        # Give seat 1 tiles that allow chi: 2m, 3m
        tile_1m = 0  # 1m
        tile_2m = 4  # 2m
        tile_3m = 8  # 3m
        tile_4m = 12  # 4m

        seat0_tiles = (tile_1m, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64)
        seat1_tiles = (tile_2m, tile_3m, tile_4m, 68, 72, 76, 80, 84, 88, 92, 96, 100, 104)
        players = [
            create_player(seat=0, tiles=seat0_tiles),
            create_player(seat=1, tiles=seat1_tiles),
            create_player(seat=2, tiles=(16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 29, 30, 31)),
            create_player(seat=3, tiles=(33, 34, 35, 37, 38, 39, 41, 42, 43, 45, 46, 47, 49)),
        ]

        round_state = create_round_state(
            players=players,
            wall=tuple(range(108, 136)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
            pending_call_prompt=PendingCallPrompt(
                call_type=CallType.MELD,
                tile_id=tile_1m,
                from_seat=0,
                pending_seats=frozenset({1}),
                callers=(MeldCaller(seat=1, call_type=MeldCallType.CHI, options=((tile_2m, tile_3m),)),),
            ),
        )
        game_state = create_game_state(round_state)
        return round_state, game_state

    def test_chi_tiles_not_in_hand(self):
        round_state, game_state = self._create_chi_state()
        data = ChiActionData(tile_id=0, sequence_tiles=(999, 8))
        with pytest.raises(InvalidGameActionError, match="not in hand"):
            handle_chi(round_state, game_state, seat=1, data=data)

    def test_chi_invalid_sequence(self):
        """Tiles don't form a valid sequence."""
        round_state, game_state = self._create_chi_state()
        # Give seat 1 a tile that doesn't form a valid sequence with 1m
        tile_7m = 24  # 7m
        new_tiles = (4, 8, tile_7m, 68, 72, 76, 80, 84, 88, 92, 96, 100, 104)
        round_state = update_player(round_state, 1, tiles=new_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        data = ChiActionData(tile_id=0, sequence_tiles=(4, tile_7m))
        with pytest.raises(InvalidGameActionError, match="valid chi sequence"):
            handle_chi(round_state, game_state, seat=1, data=data)

    def test_chi_cross_suit_boundary_raises(self):
        """Chi with tiles that span a suit boundary raises."""
        # 8m (type 7, suit 0) + 9m (type 8, suit 0) + 1p (type 9, suit 1)
        # These are numerically consecutive (7,8,9) but cross suits.
        tile_9m = 32  # type 8
        tile_8m = 28  # type 7
        tile_1p = 36  # type 9
        seat0_tiles = (tile_9m, 20, 24, 40, 44, 48, 52, 56, 60, 64, 72, 76, 80)
        seat1_tiles = (tile_8m, tile_1p, 12, 68, 84, 88, 92, 96, 100, 104, 108, 112, 116)
        players = [
            create_player(seat=0, tiles=seat0_tiles),
            create_player(seat=1, tiles=seat1_tiles),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(120, 136)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
            pending_call_prompt=PendingCallPrompt(
                call_type=CallType.MELD,
                tile_id=tile_9m,
                from_seat=0,
                pending_seats=frozenset({1}),
                callers=(MeldCaller(seat=1, call_type=MeldCallType.CHI, options=((tile_8m, tile_1p),)),),
            ),
        )
        game_state = create_game_state(round_state)
        data = ChiActionData(tile_id=tile_9m, sequence_tiles=(tile_8m, tile_1p))
        with pytest.raises(InvalidGameActionError, match="valid chi sequence"):
            handle_chi(round_state, game_state, seat=1, data=data)

    def test_chi_sequence_not_among_options(self):
        """Valid sequence that isn't among the available options."""
        round_state, game_state = self._create_chi_state()
        # Options are (2m, 3m). Give seat 1 tiles for (2m, 3m) and (3m, 4m).
        # Discarded tile is 1m. (2m,3m) with 1m = valid option.
        # Submit (3m, 4m) with 1m = 1m,3m,4m which is not consecutive -> caught earlier.
        # Instead, let's set up so the discarded tile is 2m and options allow (1m, 3m).
        # Actually, the simpler approach: change the options to not include (2m, 3m).
        prompt = round_state.pending_call_prompt
        caller = MeldCaller(
            seat=1,
            call_type=MeldCallType.CHI,
            options=((8, 12),),  # only option is (3m, 4m)
        )
        new_prompt = prompt.model_copy(
            update={"callers": (caller,)},
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": new_prompt},
        )
        game_state = game_state.model_copy(update={"round_state": round_state})
        # Submit (2m, 3m) which IS a valid sequence with 1m but NOT among options
        data = ChiActionData(tile_id=0, sequence_tiles=(4, 8))
        with pytest.raises(InvalidGameActionError, match="not among available"):
            handle_chi(round_state, game_state, seat=1, data=data)

    def test_chi_valid_sequence_succeeds(self):
        round_state, game_state = self._create_chi_state()
        data = ChiActionData(tile_id=0, sequence_tiles=(4, 8))
        result = handle_chi(round_state, game_state, seat=1, data=data)
        assert isinstance(result, ActionResult)
        # No error events
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 0


class TestPonEarlyValidation:
    """Test pon matching tiles validation."""

    def _create_pon_state(self):
        """Create state where seat 1 has a pon prompt."""
        tile_1m = 0
        tile_1m_2 = 1
        tile_1m_3 = 2

        players = [
            create_player(seat=0, tiles=(tile_1m, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64)),
            create_player(seat=1, tiles=(tile_1m_2, tile_1m_3, 8, 12, 16, 68, 72, 76, 80, 84, 88, 92, 96)),
            create_player(seat=2, tiles=(100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112)),
            create_player(seat=3, tiles=(113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125)),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(126, 136)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
            pending_call_prompt=PendingCallPrompt(
                call_type=CallType.MELD,
                tile_id=tile_1m,
                from_seat=0,
                pending_seats=frozenset({1}),
                callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
            ),
        )
        return round_state, create_game_state(round_state)

    def test_pon_not_enough_matching_tiles(self):
        round_state, game_state = self._create_pon_state()
        # Remove matching tiles from seat 1's hand
        new_tiles = (8, 12, 16, 68, 72, 76, 80, 84, 88, 92, 96, 100, 104)
        round_state = update_player(round_state, 1, tiles=new_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        with pytest.raises(InvalidGameActionError, match="not enough matching tiles"):
            handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=0))

    def test_pon_valid_succeeds(self):
        round_state, game_state = self._create_pon_state()
        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=0))
        assert isinstance(result, ActionResult)


class TestResponseActionMatchesPrompt:
    """Test that response action matches available call types in prompt."""

    def _create_meld_prompt_state(self, *, caller_type=MeldCallType.CHI):
        tile_id = 0
        players = [
            create_player(seat=0, tiles=(tile_id, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64)),
            create_player(seat=1, tiles=(4, 8, 12, 16, 68, 72, 76, 80, 84, 88, 92, 96, 100)),
            create_player(seat=2, tiles=(101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113)),
            create_player(seat=3, tiles=(114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126)),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(127, 136)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
            pending_call_prompt=PendingCallPrompt(
                call_type=CallType.MELD,
                tile_id=tile_id,
                from_seat=0,
                pending_seats=frozenset({1}),
                callers=(
                    MeldCaller(
                        seat=1,
                        call_type=caller_type,
                        options=((4, 8),) if caller_type == MeldCallType.CHI else None,
                    ),
                ),
            ),
        )
        return round_state, create_game_state(round_state)

    def test_ron_on_meld_prompt_raises(self):
        """Ron is not allowed on a meld prompt."""
        round_state, game_state = self._create_meld_prompt_state()
        with pytest.raises(InvalidGameActionError, match="cannot call ron on a meld prompt"):
            handle_ron(round_state, game_state, seat=1)

    def test_pon_caller_sends_chi_raises(self):
        """A pon-only caller sending chi action is rejected."""
        round_state, game_state = self._create_meld_prompt_state(caller_type=MeldCallType.PON)
        # seat 1 is pon caller but sends chi
        with pytest.raises(InvalidGameActionError, match="does not match available call type"):
            handle_chi(round_state, game_state, seat=1, data=ChiActionData(tile_id=0, sequence_tiles=(4, 8)))

    def test_chi_caller_sends_pon_raises(self):
        """A chi-only caller sending pon action is rejected."""
        round_state, game_state = self._create_meld_prompt_state(caller_type=MeldCallType.CHI)
        with pytest.raises(InvalidGameActionError, match="does not match available call type"):
            handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=0))

    def test_caller_not_in_prompt_raises(self):
        """Seat pending but not in callers metadata raises InvalidGameActionError."""
        round_state, game_state = self._create_meld_prompt_state(
            caller_type=MeldCallType.PON,
        )
        # Modify prompt to only have seat 2 as caller, but seat 1 is pending
        prompt = round_state.pending_call_prompt
        new_callers = (MeldCaller(seat=2, call_type=MeldCallType.PON),)
        new_prompt = prompt.model_copy(
            update={
                "callers": new_callers,
                "pending_seats": frozenset({1, 2}),
            },
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": new_prompt},
        )
        game_state = game_state.model_copy(update={"round_state": round_state})
        with pytest.raises(
            InvalidGameActionError,
            match="not present in callers metadata",
        ):
            handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=0))


class TestUnknownPromptTypeFailsClosed:
    """Validate that unknown prompt types are rejected (fail-closed)."""

    def test_unknown_prompt_type_raises(self):
        """An unrecognized prompt call_type raises InvalidGameActionError."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        # Create a fake CallType-like object with a .value attribute
        fake_call_type = type("FakeCallType", (), {"value": "unknown"})()
        mock_prompt = type(
            "FakePrompt",
            (),
            {
                "call_type": fake_call_type,
                "callers": prompt.callers,
                "pending_seats": prompt.pending_seats,
            },
        )()
        with pytest.raises(InvalidGameActionError, match="unknown prompt type"):
            _validate_caller_action_matches_prompt(mock_prompt, seat=1, action=GameAction.CALL_PON)


class TestOpenKanEarlyValidation:
    """Test open kan validation: prompt type, tile_id, tile count."""

    def _create_open_kan_state(self):
        tile_1m = 0
        players = [
            create_player(seat=0, tiles=(tile_1m, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64)),
            create_player(seat=1, tiles=(1, 2, 3, 8, 12, 68, 72, 76, 80, 84, 88, 92, 96)),
            create_player(seat=2, tiles=(100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112)),
            create_player(seat=3, tiles=(113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125)),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(126, 136)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
            pending_call_prompt=PendingCallPrompt(
                call_type=CallType.MELD,
                tile_id=tile_1m,
                from_seat=0,
                pending_seats=frozenset({1}),
                callers=(MeldCaller(seat=1, call_type=MeldCallType.OPEN_KAN),),
            ),
        )
        return round_state, create_game_state(round_state)

    def test_open_kan_no_pending_prompt_raises(self):
        """Open kan with no pending prompt raises InvalidGameActionError (fabricated data)."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        data = KanActionData(tile_id=0, kan_type=KanType.OPEN)
        with pytest.raises(InvalidGameActionError, match="open kan requires a pending call prompt"):
            handle_kan(round_state, game_state, seat=0, data=data)

    def test_open_kan_not_enough_tiles_raises(self):
        """Open kan with insufficient matching tiles raises."""
        round_state, game_state = self._create_open_kan_state()
        # Remove matching tiles
        new_tiles = (8, 12, 68, 72, 76, 80, 84, 88, 92, 96, 100, 104, 108)
        round_state = update_player(round_state, 1, tiles=new_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})
        with pytest.raises(InvalidGameActionError, match="not enough matching tiles"):
            handle_kan(round_state, game_state, seat=1, data=KanActionData(tile_id=0, kan_type=KanType.OPEN))

    def test_open_kan_tile_id_mismatch_returns_soft_error(self):
        """Open kan with wrong tile_id returns soft error (race condition)."""
        round_state, game_state = self._create_open_kan_state()
        data = KanActionData(tile_id=999, kan_type=KanType.OPEN)
        result = handle_kan(round_state, game_state, seat=1, data=data)
        assert len(result.events) == 1
        assert isinstance(result.events[0], ErrorEvent)
        assert result.events[0].code == GameErrorCode.INVALID_KAN

    def test_open_kan_on_ron_prompt_raises(self):
        """Open kan on a RON prompt (not MELD) raises."""
        round_state, game_state = self._create_open_kan_state()
        prompt = round_state.pending_call_prompt.model_copy(update={"call_type": CallType.RON})
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})
        with pytest.raises(InvalidGameActionError, match="only ron is valid on a ron prompt"):
            handle_kan(round_state, game_state, seat=1, data=KanActionData(tile_id=0, kan_type=KanType.OPEN))


class TestKanRoutingStateChecks:
    """Test CALL_KAN routing state checks."""

    def test_closed_kan_during_pending_prompt_raises(self):
        """Closed kan while a call prompt is pending raises."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        data = KanActionData(tile_id=0, kan_type=KanType.CLOSED)
        with pytest.raises(InvalidGameActionError, match="call prompt is pending"):
            handle_kan(round_state, game_state, seat=0, data=data)

    def test_added_kan_during_pending_prompt_raises(self):
        """Added kan while a call prompt is pending raises."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        with pytest.raises(InvalidGameActionError, match="call prompt is pending"):
            handle_kan(round_state, game_state, seat=0, data=KanActionData(tile_id=0, kan_type=KanType.ADDED))


class TestClosedKanRiichiWaitPreservation:
    """Test that closed kan in riichi must preserve waiting tiles."""

    def test_closed_kan_changes_waits_raises(self):
        """Closed kan in riichi that changes waits raises InvalidMeldError."""
        # Create a riichi hand where kan would change the waiting tiles
        # Hand: 1111m 234p 567s 89s - waits on 7s,9s (wait changes if we kan 1m)
        tiles_1m = TilesConverter.string_to_136_array(man="1111")
        tiles_rest = TilesConverter.string_to_136_array(pin="234", sou="56789")
        all_tiles = tuple(tiles_1m + tiles_rest)

        players = [
            create_player(seat=0, tiles=all_tiles, is_riichi=True),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(80, 100)),
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()

        with pytest.raises(InvalidMeldError, match="must not change waiting tiles"):
            call_closed_kan(round_state, 0, tiles_1m[0], settings)


class TestAddedKanRiichiRejection:
    """Test that added kan in riichi is rejected."""

    def test_added_kan_in_riichi_raises(self):
        """Added kan while in riichi raises InvalidMeldError."""
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(0, 1, 2),
            opened=True,
            who=0,
        )
        tile_4th = 3  # 4th copy of 1m
        seat0_tiles = (tile_4th, 8, 12, 16, 20, 24, 28, 32, 36, 40)
        players = [
            create_player(seat=0, tiles=seat0_tiles, melds=(pon_meld,), is_riichi=True),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(80, 100)),
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()

        with pytest.raises(InvalidMeldError, match="cannot call added kan while in riichi"):
            call_added_kan(round_state, 0, tile_4th, settings)


class TestKanExecutionGuards:
    """Test wall length and total kan count guards at execution time."""

    def test_closed_kan_wall_too_short_raises(self):
        """Closed kan with wall too short raises."""
        tiles = tuple(TilesConverter.string_to_136_array(man="1111234", pin="234", sou="56"))
        players = [
            create_player(seat=0, tiles=tiles),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=(130,),  # only 1 tile, need at least 2
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()
        tile_1m = TilesConverter.string_to_136_array(man="1")[0]

        with pytest.raises(InvalidMeldError, match="not enough tiles in wall"):
            call_closed_kan(round_state, 0, tile_1m, settings)

    def test_added_kan_wall_too_short_raises(self):
        """Added kan with wall too short raises."""
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(0, 1, 2),
            opened=True,
            who=0,
        )
        players = [
            create_player(seat=0, tiles=(3, 8, 12, 16, 20, 24, 28, 32, 36, 40), melds=(pon_meld,)),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=(130,),
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()

        with pytest.raises(InvalidMeldError, match="not enough tiles in wall"):
            call_added_kan(round_state, 0, 3, settings)

    def test_added_kan_total_kans_at_limit_raises(self):
        """Added kan when 4 kans already declared raises."""
        kan1 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(4, 5, 6, 7), opened=False, who=0)
        kan2 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(8, 9, 10, 11), opened=False, who=0)
        kan3 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(12, 13, 14, 15), opened=False, who=0)
        kan4 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(16, 17, 18, 19), opened=False, who=0)
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=(0, 1, 2),
            opened=True,
            who=0,
        )
        melds = (kan1, kan2, kan3, kan4, pon_meld)
        players = [
            create_player(seat=0, tiles=(3, 24, 28, 32, 36, 40), melds=melds),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(80, 100)),
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()

        with pytest.raises(InvalidMeldError, match="maximum kans per round"):
            call_added_kan(round_state, 0, 3, settings)

    def test_closed_kan_total_kans_at_limit_raises(self):
        """Closed kan when 4 kans already declared raises."""
        kan1 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(0, 1, 2, 3), opened=False, who=0)
        kan2 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(4, 5, 6, 7), opened=False, who=0)
        kan3 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(8, 9, 10, 11), opened=False, who=0)
        kan4 = FrozenMeld(meld_type=FrozenMeld.KAN, tiles=(12, 13, 14, 15), opened=False, who=0)

        tiles = tuple(TilesConverter.string_to_136_array(man="5555"))
        players = [
            create_player(seat=0, tiles=tiles, melds=(kan1, kan2, kan3, kan4)),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(80, 100)),
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()
        tile_5m = TilesConverter.string_to_136_array(man="5")[0]

        with pytest.raises(InvalidMeldError, match="maximum kans per round"):
            call_closed_kan(round_state, 0, tile_5m, settings)


class TestRiichiDiscardTenpaiValidation:
    """Test that riichi discard keeps hand in tenpai."""

    def test_riichi_discard_breaks_tenpai_raises(self):
        """Riichi with a discard that breaks tenpai raises."""
        # Hand: 112345m 456p 789s 11z (14 tiles)
        # can_declare_riichi passes because discarding 5m keeps tenpai
        # But discarding 3m (tile 8) breaks tenpai
        all_tiles = tuple(TilesConverter.string_to_136_array(man="112345", pin="456", sou="789", honors="11"))
        assert len(all_tiles) == 14

        players = [
            create_player(seat=0, tiles=all_tiles, score=25000),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(80, 100)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
        )
        game_state = create_game_state(round_state)

        # Discard 3m (tile 8) - breaks tenpai
        with pytest.raises(InvalidGameActionError, match="not tenpai"):
            handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=8))

    def test_riichi_valid_discard_succeeds(self):
        """Riichi with a valid tenpai-preserving discard succeeds."""
        # Hand: 112345m 456p 789s 11z (14 tiles)
        # Discarding 5m (tile 16) preserves tenpai
        all_tiles = tuple(TilesConverter.string_to_136_array(man="112345", pin="456", sou="789", honors="11"))
        assert len(all_tiles) == 14

        players = [
            create_player(seat=0, tiles=all_tiles, score=25000),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(80, 100)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
        )
        game_state = create_game_state(round_state)

        # Discarding 5m (tile 16) preserves tenpai
        result = handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=16))
        assert isinstance(result, ActionResult)
        assert result.needs_post_discard is True


class TestKyuushuRuleGate:
    """Test kyuushu rule gate and hard-invalid classification."""

    def test_kyuushu_disabled_raises(self):
        """Kyuushu when rule is disabled raises InvalidGameActionError."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        settings = GameSettings(has_kyuushu_kyuuhai=False)
        game_state = game_state.model_copy(update={"settings": settings})

        with pytest.raises(InvalidGameActionError, match="disabled by game settings"):
            handle_kyuushu(round_state, game_state, seat=0)

    def test_kyuushu_conditions_not_met_raises(self):
        """Kyuushu when conditions not met raises InvalidGameActionError."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # Add discards so kyuushu conditions are not met
        round_state = update_player(round_state, 0, discards=(Discard(tile_id=0),))
        game_state = game_state.model_copy(update={"round_state": round_state})

        with pytest.raises(InvalidGameActionError, match="conditions not met"):
            handle_kyuushu(round_state, game_state, seat=0)

    def test_kyuushu_wrong_turn_returns_error_event(self):
        """Kyuushu wrong turn still returns soft ErrorEvent (race condition)."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_kyuushu(round_state, game_state, seat=1)
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN


class TestPendingCallPromptStateGate:
    """Test that turn actions are rejected while a call prompt is pending."""

    async def test_discard_during_pending_prompt_raises(self):
        """Discard while a call prompt is pending raises InvalidGameActionError."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING},
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        service = MahjongGameService()
        service._games["test"] = game_state
        service._bot_controllers["test"] = BotController({})

        with pytest.raises(InvalidGameActionError, match=r"turn action.*call prompt is pending"):
            await service.handle_action("test", "Player", GameAction.DISCARD, {"tile_id": 0})


class TestCallChiDefenseInDepth:
    """Test call_chi() raises InvalidMeldError for tiles not in hand."""

    def test_chi_tile_not_in_hand_raises_meld_error(self):
        """call_chi with tile not in hand raises InvalidMeldError."""
        players = [
            create_player(seat=0, tiles=(0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48)),
            create_player(seat=1, tiles=(52, 56, 60, 64, 68, 72, 76, 80, 84, 88, 92, 96, 100)),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(104, 136)),
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()

        # Try chi with tiles not in hand (999, 998)
        with pytest.raises(InvalidMeldError, match="not found in hand"):
            call_chi(round_state, 1, 0, 0, (999, 998), settings)


class TestSoftErrorsRemainUnchanged:
    """Verify race-condition timing errors still return soft ErrorEvent."""

    def test_not_your_turn_returns_error_event(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_discard(round_state, game_state, seat=1, data=DiscardActionData(tile_id=0))
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN

    def test_no_pending_prompt_returns_error_event(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_ron(round_state, game_state, seat=0)
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_RON

    def test_pass_no_prompt_returns_error_event(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_pass(round_state, game_state, seat=0)
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_PASS

    def test_pon_tile_mismatch_returns_error_event(self):
        """Tile_id mismatch is a race condition (prompt may have changed)."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # Send wrong tile_id - this is a race condition
        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=999))
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_PON

    def test_non_pending_seat_returns_error_event(self):
        """Non-pending seat sending response is a race condition."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(1,),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # Seat 2 is not pending
        result = handle_ron(round_state, game_state, seat=2)
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_RON


class TestOpenKanRiichiGuard:
    """Test defense-in-depth: open kan from riichi player is rejected."""

    def test_open_kan_execution_rejects_riichi_player(self):
        """call_open_kan rejects riichi player at execution time."""
        players = [
            create_player(seat=0, tiles=(0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48)),
            create_player(seat=1, tiles=(1, 2, 3, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88), is_riichi=True),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(92, 136)),
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()

        with pytest.raises(InvalidMeldError, match="cannot call open kan while in riichi"):
            call_open_kan(round_state, 1, 0, 0, settings)


# --- Phase 3: Error Handling Conversion Tests ---


class TestDiscardRaisesInvalidGameActionError:
    """Test that discard with invalid data raises InvalidGameActionError."""

    def test_discard_tile_not_in_hand(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        with pytest.raises(InvalidGameActionError, match="discard") as exc_info:
            handle_discard(round_state, game_state, seat=0, data=DiscardActionData(tile_id=999))
        assert exc_info.value.seat == 0

    def test_discard_wrong_turn_still_soft_error(self):
        """Wrong turn remains soft ErrorEvent (race condition)."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        result = handle_discard(round_state, game_state, seat=1, data=DiscardActionData(tile_id=0))
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN


class TestRiichiRaisesInvalidGameActionError:
    """Test that riichi with invalid data raises InvalidGameActionError."""

    def test_riichi_tile_not_in_hand(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        with pytest.raises(InvalidGameActionError, match="declare_riichi") as exc_info:
            handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=999))
        assert exc_info.value.seat == 0

    def test_riichi_already_in_riichi(self):
        """Riichi when already in riichi raises InvalidGameActionError."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        round_state = update_player(round_state, 0, is_riichi=True)
        game_state = game_state.model_copy(update={"round_state": round_state})
        tile_id = round_state.players[0].tiles[0]
        with pytest.raises(InvalidGameActionError, match="declare_riichi"):
            handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=tile_id))

    def test_riichi_not_enough_points(self):
        """Riichi with insufficient points raises InvalidGameActionError."""
        all_tiles = tuple(TilesConverter.string_to_136_array(man="112345", pin="456", sou="789", honors="11"))
        players = [
            create_player(seat=0, tiles=all_tiles, score=500),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(80, 100)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
        )
        game_state = create_game_state(round_state)
        with pytest.raises(InvalidGameActionError, match="declare_riichi"):
            handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=all_tiles[0]))

    def test_riichi_open_hand(self):
        """Riichi with open melds raises InvalidGameActionError."""
        pon_meld = FrozenMeld(meld_type=FrozenMeld.PON, tiles=(0, 1, 2), opened=True, who=0)
        all_tiles = tuple(TilesConverter.string_to_136_array(man="12345", pin="456", sou="789", honors="1"))
        players = [
            create_player(seat=0, tiles=all_tiles, melds=(pon_meld,), score=25000),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(80, 100)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
        )
        game_state = create_game_state(round_state)
        with pytest.raises(InvalidGameActionError, match="declare_riichi"):
            handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=all_tiles[0]))


class TestTsumoRaisesInvalidGameActionError:
    """Test that tsumo with non-winning hand raises InvalidGameActionError."""

    def test_tsumo_not_winning(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        with pytest.raises(InvalidGameActionError, match="declare_tsumo") as exc_info:
            handle_tsumo(round_state, game_state, seat=0)
        assert exc_info.value.seat == 0


class TestKanRaisesInvalidGameActionError:
    """Test that kan with invalid data raises InvalidGameActionError."""

    def test_closed_kan_not_enough_tiles(self):
        """Closed kan without 4 matching tiles raises InvalidGameActionError."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        data = KanActionData(tile_id=0, kan_type=KanType.CLOSED)
        with pytest.raises(InvalidGameActionError, match="call_kan"):
            handle_kan(round_state, game_state, seat=0, data=data)


class TestResolutionSafetyNet:
    """Test the resolve_call_prompt safety net and blame attribution."""

    def test_resolution_blame_attributes_correct_seat(self):
        """When resolution fails, the offending seat is identified from responses."""
        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(1, 2),
            responses=(CallResponse(seat=1, action=GameAction.CALL_RON),),
        )
        # Ron caller (seat 1) should be identified as offender, not fallback (seat 3)
        assert _find_offending_seat_from_prompt(prompt, fallback_seat=3) == 1

    def test_resolution_blame_meld_response(self):
        """Meld response identified when no ron responses."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=2, call_type=MeldCallType.PON),),
            responses=(CallResponse(seat=2, action=GameAction.CALL_PON),),
        )
        assert _find_offending_seat_from_prompt(prompt, fallback_seat=3) == 2

    def test_resolution_blame_fallback(self):
        """Fallback seat used when no actionable responses."""
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
            responses=(),
        )
        assert _find_offending_seat_from_prompt(prompt, fallback_seat=3) == 3


class TestResolutionSafetyNetExecution:
    """Test that the safety net catches GameRuleError at resolution time."""

    def test_resolve_call_prompt_safe_catches_error(self):
        """_resolve_call_prompt_safe catches GameRuleError and raises InvalidGameActionError."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.PON),),
            responses=(CallResponse(seat=1, action=GameAction.CALL_PON),),
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING},
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        with patch(
            "game.logic.action_handlers.resolve_call_prompt",
            side_effect=GameRuleError("test error"),
        ):
            with pytest.raises(InvalidGameActionError, match="test error") as exc_info:
                _resolve_call_prompt_safe(round_state, game_state, prompt, triggering_seat=3)
            # Blame should go to the pon caller (seat 1), not the triggering seat (3)
            assert exc_info.value.seat == 1
            assert exc_info.value.action == "resolve_call"

    def test_handle_pass_resolution_catches_error(self):
        """handle_pass catches GameRuleError during resolution and raises InvalidGameActionError."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # Create prompt where seat 3 passes (the last pending seat)
        # and seat 1 has a chi response that fails at resolution
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({3}),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.CHI, options=((4, 8),)),
                3,
            ),
            responses=(CallResponse(seat=1, action=GameAction.CALL_CHI, sequence_tiles=(4, 8)),),
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING},
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        with patch(
            "game.logic.action_handlers.resolve_call_prompt",
            side_effect=GameRuleError("chi resolution failed"),
        ):
            with pytest.raises(InvalidGameActionError) as exc_info:
                handle_pass(round_state, game_state, seat=3)
            # Blame should go to the chi caller (seat 1), not the passer (seat 3)
            assert exc_info.value.seat == 1
            assert exc_info.value.action == "resolve_call"


class TestBotSafetyNets:
    """Test bot processing safety nets catch InvalidGameActionError."""

    async def test_bot_call_response_catches_invalid_action(self):
        """Bot call response that triggers InvalidGameActionError is caught, not propagated."""
        service = MahjongGameService()
        await service.start_game("test", ["Human"], seed=42.0)

        game_state = service._games["test"]
        bot_controller = service._bot_controllers["test"]
        bot_seats = sorted(bot_controller.bot_seats)

        # Set up a pending prompt for a bot
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({bot_seats[0]}),
            callers=(MeldCaller(seat=bot_seats[0], call_type=MeldCallType.PON),),
        )
        round_state = game_state.round_state.model_copy(
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING},
        )
        service._games["test"] = game_state.model_copy(update={"round_state": round_state})

        # Make _dispatch_action raise InvalidGameActionError
        with patch.object(
            service,
            "_dispatch_action",
            side_effect=InvalidGameActionError(action="call_pon", seat=bot_seats[0], reason="test"),
        ):
            events = []
            service._dispatch_bot_call_responses("test", events)

        # The safety net should have caught the error - no propagation
        # The prompt should still be there since the bot response was not processed
        assert service._games["test"].round_state.pending_call_prompt is not None

    async def test_bot_call_action_falls_back_to_pass(self):
        """Bot call action falls back to PASS when the initial non-PASS action fails."""
        service = MahjongGameService()
        await service.start_game("test", ["Human"], seed=42.0)

        game_state = service._games["test"]
        bot_controller = service._bot_controllers["test"]
        bot_seat = sorted(bot_controller.bot_seats)[0]

        with patch.object(
            service,
            "_dispatch_action",
            side_effect=InvalidGameActionError(action="call_pon", seat=bot_seat, reason="test"),
        ):
            result = service._dispatch_bot_call_action("test", game_state, bot_seat, GameAction.CALL_PON, {})
        assert result is None

    async def test_bot_call_action_pass_fallback_reraises_when_offender_is_human(self):
        """Bot PASS fallback re-raises when the error blames a different seat."""
        service = MahjongGameService()
        await service.start_game("test", ["Human"], seed=42.0)

        game_state = service._games["test"]
        bot_controller = service._bot_controllers["test"]
        bot_seat = sorted(bot_controller.bot_seats)[0]
        human_seat = 0

        with (
            patch.object(
                service,
                "_dispatch_action",
                side_effect=[
                    # First call (non-PASS action) fails with bot's own seat
                    InvalidGameActionError(action="call_pon", seat=bot_seat, reason="bot error"),
                    # Second call (PASS fallback) fails with human seat (resolution blame)
                    InvalidGameActionError(action="resolve_call", seat=human_seat, reason="human error"),
                ],
            ),
            pytest.raises(InvalidGameActionError, match="human error"),
        ):
            service._dispatch_bot_call_action("test", game_state, bot_seat, GameAction.CALL_PON, {})

    async def test_bot_call_response_reraises_when_offender_is_human(self):
        """Bot call response re-raises InvalidGameActionError when the offending seat is a human."""
        service = MahjongGameService()
        await service.start_game("test", ["Human"], seed=42.0)

        game_state = service._games["test"]
        bot_controller = service._bot_controllers["test"]
        bot_seats = sorted(bot_controller.bot_seats)
        human_seat = 0  # seat 0 is the human

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=3,
            pending_seats=frozenset({bot_seats[0]}),
            callers=(MeldCaller(seat=bot_seats[0], call_type=MeldCallType.PON),),
        )
        round_state = game_state.round_state.model_copy(
            update={"pending_call_prompt": prompt, "phase": RoundPhase.PLAYING},
        )
        service._games["test"] = game_state.model_copy(update={"round_state": round_state})

        # Error blames human seat (e.g. resolution failed on human's bad data)
        with patch.object(
            service,
            "_dispatch_action",
            side_effect=InvalidGameActionError(action="resolve_call", seat=human_seat, reason="test"),
        ):
            events = []
            with pytest.raises(InvalidGameActionError, match="resolve_call"):
                service._dispatch_bot_call_responses("test", events)

    async def test_bot_followup_catches_invalid_action(self):
        """Bot followup that triggers InvalidGameActionError is caught, not propagated."""
        service = MahjongGameService()
        await service.start_game("test", ["Human"], seed=42.0)

        # Make the current seat a bot so the followup loop enters
        game_state = service._games["test"]
        bot_controller = service._bot_controllers["test"]
        current_seat = game_state.round_state.current_player_seat

        # If the current player is not a bot, make them one
        if not bot_controller.is_bot(current_seat):
            bot_controller.add_bot(current_seat, BotPlayer(strategy=BotStrategy.TSUMOGIRI))

        # Make _dispatch_and_process raise InvalidGameActionError
        with patch.object(
            service,
            "_dispatch_and_process",
            side_effect=InvalidGameActionError(action="discard", seat=current_seat, reason="test"),
        ):
            events = await service._process_bot_followup("test")

        # The safety net caught the error - returned whatever was accumulated
        assert isinstance(events, list)

    async def test_bot_followup_reraises_when_offender_is_human(self):
        """Bot followup re-raises InvalidGameActionError when the offending seat is a human."""
        service = MahjongGameService()
        await service.start_game("test", ["Human"], seed=42.0)

        game_state = service._games["test"]
        bot_controller = service._bot_controllers["test"]
        # Use an existing bot seat (not the human seat 0) as current player
        bot_seat = sorted(bot_controller.bot_seats)[0]
        human_seat = 0
        assert bot_seat != human_seat

        # Make the bot the current player
        round_state = game_state.round_state.model_copy(update={"current_player_seat": bot_seat})
        service._games["test"] = game_state.model_copy(update={"round_state": round_state})

        # Error blames the human seat (e.g. resolution failed on human's bad data)
        with (
            patch.object(
                service,
                "_dispatch_and_process",
                side_effect=InvalidGameActionError(action="resolve_call", seat=human_seat, reason="test"),
            ),
            pytest.raises(InvalidGameActionError, match="resolve_call"),
        ):
            await service._process_bot_followup("test")

    async def test_bot_tsumogiri_fallback_game_cleaned_up(self):
        """_bot_tsumogiri_fallback returns None if game state is cleaned up."""
        service = MahjongGameService()
        result = await service._bot_tsumogiri_fallback("nonexistent", 0)
        assert result is None

    async def test_bot_tsumogiri_fallback_no_tiles(self):
        """_bot_tsumogiri_fallback returns None if player has no tiles."""
        service = MahjongGameService()
        await service.start_game("test", ["Human"], seed=42.0)

        game_state = service._games["test"]
        current_seat = game_state.round_state.current_player_seat
        # Remove tiles from the current player
        empty_player = game_state.round_state.players[current_seat].model_copy(update={"tiles": ()})
        players = list(game_state.round_state.players)
        players[current_seat] = empty_player
        round_state = game_state.round_state.model_copy(update={"players": tuple(players)})
        service._games["test"] = game_state.model_copy(update={"round_state": round_state})

        result = await service._bot_tsumogiri_fallback("test", current_seat)
        assert result is None

    async def test_bot_tsumogiri_fallback_reraises_when_offender_is_human(self):
        """_bot_tsumogiri_fallback re-raises when the error blames a different seat."""
        service = MahjongGameService()
        await service.start_game("test", ["Human"], seed=42.0)

        bot_controller = service._bot_controllers["test"]
        bot_seat = sorted(bot_controller.bot_seats)[0]
        human_seat = 0

        with (
            patch.object(
                service,
                "_dispatch_and_process",
                side_effect=InvalidGameActionError(action="resolve_call", seat=human_seat, reason="test"),
            ),
            pytest.raises(InvalidGameActionError, match="resolve_call"),
        ):
            await service._bot_tsumogiri_fallback("test", bot_seat)


class TestOpenKanDefenseInDepthGuards:
    """Test defense-in-depth: call_open_kan wall and kan count guards."""

    def test_open_kan_insufficient_wall_raises(self):
        """call_open_kan with too few wall tiles raises InvalidMeldError."""
        tile_5m = TilesConverter.string_to_136_array(man="5")[0]
        players = [
            create_player(seat=0, tiles=(0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48)),
            create_player(seat=1, tiles=(1, 2, 3, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88)),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=(90,),  # only 1 tile, below min_wall_for_kan=2
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()

        with pytest.raises(InvalidMeldError, match="not enough tiles in wall for kan"):
            call_open_kan(round_state, 1, 0, tile_5m, settings)

    def test_open_kan_max_kans_exceeded_raises(self):
        """call_open_kan when total kans >= max_kans_per_round raises InvalidMeldError."""
        tile_5m = TilesConverter.string_to_136_array(man="5")[0]
        # Create 4 existing kan melds (max_kans_per_round default = 4)
        kan_melds = tuple(
            FrozenMeld(
                meld_type=FrozenMeld.KAN,
                tiles=tuple(TilesConverter.string_to_136_array(man=str(i + 1) * 4)),
                opened=True,
                who=0,
                from_who=0,
            )
            for i in range(4)
        )
        players = [
            create_player(seat=0, tiles=(0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44, 48), melds=kan_melds),
            create_player(seat=1, tiles=(1, 2, 3, 52, 56, 60, 64, 68, 72, 76, 80, 84, 88)),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(92, 110)),
            dead_wall=tuple(range(50, 64)),
            phase=RoundPhase.PLAYING,
        )
        settings = GameSettings()

        with pytest.raises(InvalidMeldError, match="maximum kans per round reached"):
            call_open_kan(round_state, 1, 0, tile_5m, settings)


class TestRiichiTileNotInHandValidation:
    """Test that riichi with tile not in hand raises InvalidGameActionError (via InvalidRiichiError)."""

    def test_riichi_tenpai_hand_wrong_tile_raises(self):
        """Riichi with tenpai hand but tile_id not in hand raises InvalidGameActionError."""
        # Hand: 112345m 456p 789s 11z (14 tiles) - this is tenpai
        all_tiles = tuple(TilesConverter.string_to_136_array(man="112345", pin="456", sou="789", honors="11"))
        assert len(all_tiles) == 14

        players = [
            create_player(seat=0, tiles=all_tiles, score=25000),
            create_player(seat=1),
            create_player(seat=2),
            create_player(seat=3),
        ]
        round_state = create_round_state(
            players=players,
            wall=tuple(range(80, 100)),
            dead_wall=tuple(range(50, 64)),
            current_player_seat=0,
            phase=RoundPhase.PLAYING,
        )
        game_state = create_game_state(round_state)

        # tile_id 999 is not in hand (but hand IS tenpai so can_declare_riichi passes)
        with pytest.raises(InvalidGameActionError, match="not in hand"):
            handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=999))


class TestFindMeldCallerForSeatNone:
    """Test that inconsistent prompt state (seat pending but not in callers) fails closed."""

    def test_chi_raises_when_seat_not_in_callers(self):
        """Chi raises InvalidGameActionError when seat is pending but not in callers."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        tile_id = TilesConverter.string_to_136_array(man="5")[0]
        player1_tiles = list(round_state.players[1].tiles)

        chi_tiles = TilesConverter.string_to_136_array(man="46")
        player1_tiles = list(chi_tiles) + [t for t in player1_tiles if t not in chi_tiles][:11]
        round_state = update_player(round_state, 1, tiles=tuple(player1_tiles))

        # Seat 1 is pending but callers only list seat 2
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(
                MeldCaller(
                    seat=2,
                    call_type=MeldCallType.CHI,
                    options=(chi_tiles,),
                ),
            ),
            responses=(),
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": prompt},
        )
        game_state = game_state.model_copy(
            update={"round_state": round_state},
        )

        with pytest.raises(
            InvalidGameActionError,
            match="not present in callers metadata",
        ):
            handle_chi(
                round_state,
                game_state,
                seat=1,
                data=ChiActionData(tile_id=tile_id, sequence_tiles=chi_tiles),
            )
