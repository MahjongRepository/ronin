from unittest.mock import patch

import pytest
from mahjong.tile import TilesConverter

from game.logic.action_handlers import (
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
from game.logic.ai_player import AIPlayer
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import (
    AIPlayerType,
    CallType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldCallType,
    RoundPhase,
    TimeoutType,
)
from game.logic.events import ErrorEvent
from game.logic.exceptions import GeneratedActionError, InvalidGameActionError, InvalidMeldError
from game.logic.game import init_game
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.melds import (
    call_added_kan,
    call_chi,
    call_closed_kan,
    call_open_kan,
    validate_closed_kan,
)
from game.logic.round import draw_tile
from game.logic.settings import GameSettings
from game.logic.state import (
    Discard,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.tiles import tile_to_34
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
from game.tests.unit.helpers import _update_player


def _default_seat_configs():
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="AI1", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="AI2", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="AI3", ai_player_type=AIPlayerType.TSUMOGIRI),
    ]


def _create_frozen_game_state():
    game_state = init_game(_default_seat_configs(), wall=list(range(136)))
    new_round_state, _tile = draw_tile(game_state.round_state)
    return game_state.model_copy(update={"round_state": new_round_state})


class TestChiEarlyValidation:
    def _create_chi_state(self):
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

    def test_chi_validation__when_tiles_not_in_hand__should_raise(self):
        round_state, game_state = self._create_chi_state()
        data = ChiActionData(tile_id=0, sequence_tiles=(999, 8))
        with pytest.raises(InvalidGameActionError, match="not in hand"):
            handle_chi(round_state, game_state, seat=1, data=data)

    def test_chi_validation__when_invalid_sequence__should_raise(self):
        round_state, game_state = self._create_chi_state()
        # Give seat 1 a tile that doesn't form a valid sequence with 1m
        tile_7m = 24  # 7m
        new_tiles = (4, 8, tile_7m, 68, 72, 76, 80, 84, 88, 92, 96, 100, 104)
        round_state = update_player(round_state, 1, tiles=new_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        data = ChiActionData(tile_id=0, sequence_tiles=(4, tile_7m))
        with pytest.raises(InvalidGameActionError, match="valid chi sequence"):
            handle_chi(round_state, game_state, seat=1, data=data)

    def test_chi_validation__when_sequence_crosses_suit_boundary__should_raise(self):
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

    def test_chi_validation__when_sequence_not_among_options_and_pon_also_offered__should_raise(self):
        round_state, game_state = self._create_chi_state()
        prompt = round_state.pending_call_prompt
        pon_caller = MeldCaller(seat=1, call_type=MeldCallType.PON)
        chi_caller_offered_only_3m_4m = MeldCaller(seat=1, call_type=MeldCallType.CHI, options=((8, 12),))
        new_prompt = prompt.model_copy(
            update={"callers": (pon_caller, chi_caller_offered_only_3m_4m)},
        )
        round_state = round_state.model_copy(
            update={"pending_call_prompt": new_prompt},
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        # Submit (2m, 3m) which IS a valid sequence with 1m but NOT among options
        data = ChiActionData(tile_id=0, sequence_tiles=(4, 8))
        with pytest.raises(InvalidGameActionError, match="not among available"):
            handle_chi(round_state, game_state, seat=1, data=data)

    def test_chi_validation__when_valid_sequence__should_succeed(self):
        round_state, game_state = self._create_chi_state()
        data = ChiActionData(tile_id=0, sequence_tiles=(4, 8))

        result = handle_chi(round_state, game_state, seat=1, data=data)
        assert isinstance(result, ActionResult)
        # No error events
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 0


class TestPonEarlyValidation:
    def _create_pon_state(self):
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

    def test_pon_validation__when_not_enough_matching_tiles__should_raise(self):
        round_state, game_state = self._create_pon_state()
        # Remove matching tiles from seat 1's hand
        new_tiles = (8, 12, 16, 68, 72, 76, 80, 84, 88, 92, 96, 100, 104)
        round_state = update_player(round_state, 1, tiles=new_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        with pytest.raises(InvalidGameActionError, match="not enough matching tiles"):
            handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=0))

    def test_pon_validation__when_valid__should_succeed(self):
        round_state, game_state = self._create_pon_state()
        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=0))
        assert isinstance(result, ActionResult)


class TestResponseActionMatchesPrompt:
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

    def test_response_action__when_ron_on_meld_prompt__should_raise(self):
        round_state, game_state = self._create_meld_prompt_state()
        with pytest.raises(InvalidGameActionError, match="cannot call ron on a meld prompt"):
            handle_ron(round_state, game_state, seat=1)

    def test_response_action__when_pon_caller_sends_chi__should_raise(self):
        round_state, game_state = self._create_meld_prompt_state(caller_type=MeldCallType.PON)
        # seat 1 is pon caller but sends chi
        with pytest.raises(InvalidGameActionError, match="does not match available call type"):
            handle_chi(round_state, game_state, seat=1, data=ChiActionData(tile_id=0, sequence_tiles=(4, 8)))

    def test_response_action__when_chi_caller_sends_pon__should_raise(self):
        round_state, game_state = self._create_meld_prompt_state(caller_type=MeldCallType.CHI)
        with pytest.raises(InvalidGameActionError, match="does not match available call type"):
            handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=0))

    def test_response_action__when_caller_not_in_prompt__should_raise(self):
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
            match="no meld options for this seat",
        ):
            handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=0))


class TestOpenKanEarlyValidation:
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

    def test_open_kan_validation__when_no_pending_prompt__should_return_error(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        data = KanActionData(tile_id=0, kan_type=KanType.OPEN)

        result = handle_kan(round_state, game_state, seat=0, data=data)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_KAN

    def test_open_kan_validation__when_not_enough_tiles__should_raise(self):
        round_state, game_state = self._create_open_kan_state()
        # Remove matching tiles
        new_tiles = (8, 12, 68, 72, 76, 80, 84, 88, 92, 96, 100, 104, 108)
        round_state = update_player(round_state, 1, tiles=new_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        with pytest.raises(InvalidGameActionError, match="not enough matching tiles"):
            handle_kan(round_state, game_state, seat=1, data=KanActionData(tile_id=0, kan_type=KanType.OPEN))

    def test_open_kan_validation__when_tile_id_mismatches_prompt__should_return_soft_error(self):
        round_state, game_state = self._create_open_kan_state()
        data = KanActionData(tile_id=999, kan_type=KanType.OPEN)

        result = handle_kan(round_state, game_state, seat=1, data=data)
        assert len(result.events) == 1
        assert isinstance(result.events[0], ErrorEvent)
        assert result.events[0].code == GameErrorCode.INVALID_KAN

    def test_open_kan_validation__when_ron_prompt__should_raise(self):
        round_state, game_state = self._create_open_kan_state()
        prompt = round_state.pending_call_prompt.model_copy(update={"call_type": CallType.RON})
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        with pytest.raises(InvalidGameActionError, match="only ron is valid"):
            handle_kan(round_state, game_state, seat=1, data=KanActionData(tile_id=0, kan_type=KanType.OPEN))


class TestClosedKanRiichiWaitPreservation:
    def test_closed_kan_riichi__when_drawn_tile_not_kan_tile__should_raise(self):
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

        with pytest.raises(InvalidMeldError, match="drawn tile must be the kan tile"):
            call_closed_kan(round_state, seat=0, tile_id=tiles_1m[0], settings=settings)

    def test_closed_kan_riichi__when_waits_change__should_raise(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        man_rest = TilesConverter.string_to_136_array(man="2345678999")
        all_tiles = tuple(list(man_1m[:3]) + list(man_rest) + [man_1m[3]])

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
            call_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=settings)


class TestValidateClosedKanRiichi:
    def test_validate_closed_kan_riichi__when_drawn_tile_not_kan_tile__should_reject(self):
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

        with pytest.raises(InvalidMeldError, match="drawn tile must be the kan tile"):
            validate_closed_kan(round_state, seat=0, tile_id=tiles_1m[0], settings=GameSettings())

    def test_validate_closed_kan_riichi__when_waits_change__should_reject(self):
        man_1m = TilesConverter.string_to_136_array(man="1111")
        man_rest = TilesConverter.string_to_136_array(man="2345678999")
        all_tiles = tuple(list(man_1m[:3]) + list(man_rest) + [man_1m[3]])

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

        with pytest.raises(InvalidMeldError, match="must not change waiting tiles"):
            validate_closed_kan(round_state, seat=0, tile_id=man_1m[0], settings=GameSettings())


class TestAddedKanRiichiRejection:
    def test_added_kan__when_player_in_riichi__should_raise(self):
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
            call_added_kan(round_state, seat=0, tile_id=tile_4th, settings=settings)


class TestKanExecutionGuards:
    def test_closed_kan__when_wall_too_short__should_raise(self):
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
            call_closed_kan(round_state, seat=0, tile_id=tile_1m, settings=settings)

    def test_added_kan__when_wall_too_short__should_raise(self):
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
            call_added_kan(round_state, seat=0, tile_id=3, settings=settings)

    def test_added_kan__when_total_kans_at_limit__should_raise(self):
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
            call_added_kan(round_state, seat=0, tile_id=3, settings=settings)

    def test_closed_kan__when_total_kans_at_limit__should_raise(self):
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
            call_closed_kan(round_state, seat=0, tile_id=tile_5m, settings=settings)


class TestRiichiDiscardTenpaiValidation:
    def test_riichi_discard__when_discard_breaks_tenpai__should_answer_invalid_riichi_and_keep_the_turn(self):
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
        result = handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=8))
        assert [(e.code, e.target) for e in result.events] == [(GameErrorCode.INVALID_RIICHI, "seat_0")]
        assert result.new_round_state is round_state
        assert result.needs_post_discard is False

    def test_riichi_discard__when_discard_keeps_tenpai__should_succeed(self):
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
    def test_kyuushu_kyuuhai__when_conditions_not_met__should_raise(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # Add discards so kyuushu conditions are not met
        round_state = update_player(round_state, 0, discards=(Discard(tile_id=0),))
        game_state = game_state.model_copy(update={"round_state": round_state})

        with pytest.raises(InvalidGameActionError, match="conditions not met"):
            handle_kyuushu(round_state, game_state, seat=0)

    def test_kyuushu_kyuuhai__when_not_players_turn__should_return_error_event(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_kyuushu(round_state, game_state, seat=1)
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN


class TestPendingCallPromptStateGate:
    @pytest.mark.parametrize(
        ("action", "data"),
        [
            (GameAction.DISCARD, {"tile_id": "own"}),
            (GameAction.DECLARE_RIICHI, {"tile_id": "own"}),
            (GameAction.DECLARE_TSUMO, {}),
            (GameAction.CALL_KYUUSHU, {}),
            (GameAction.CALL_KAN, {"tile_id": "own", "kan_type": KanType.CLOSED}),
            (GameAction.CALL_KAN, {"tile_id": "own", "kan_type": KanType.ADDED}),
        ],
        ids=["discard", "riichi", "tsumo", "kyuushu", "closed_kan", "added_kan"],
    )
    def test_turn_action__when_prompt_pending__should_answer_not_your_turn_without_kick(self, action, data):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        own_tile = round_state.players[0].tiles[-1]

        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
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
        service._ai_player_controllers["test"] = AIPlayerController({})
        service._furiten_tracker.init_game("test")

        action_data = {key: own_tile if value == "own" else value for key, value in data.items()}
        events = service.handle_action(game_id="test", player_name="Player", action=action, data=action_data)
        assert [(e.data.code, e.data.target) for e in events] == [(GameErrorCode.NOT_YOUR_TURN, "seat_0")]
        assert service._games["test"] is game_state


class TestCallChiDefenseInDepth:
    def test_call_chi__when_tile_not_in_hand__should_raise_meld_error(self):
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

        with pytest.raises(InvalidMeldError, match="not found in hand"):
            call_chi(round_state, caller_seat=1, discarder_seat=0, tile_id=0, sequence_tiles=(5, 9), settings=settings)


class TestSoftErrorsRemainUnchanged:
    @pytest.mark.parametrize("forbidding_rule", ["kuikae", "riichi_tsumogiri"])
    def test_discard__when_rule_forbids_the_tile__should_answer_invalid_discard_and_keep_the_turn(
        self, forbidding_rule
    ):
        game_state = _create_frozen_game_state()
        first_tile = game_state.round_state.players[0].tiles[0]
        fields = {"kuikae_tiles": (tile_to_34(first_tile),)} if forbidding_rule == "kuikae" else {"is_riichi": True}
        round_state = update_player(game_state.round_state, 0, **fields)
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = handle_discard(round_state, game_state, seat=0, data=DiscardActionData(tile_id=first_tile))
        assert [(e.code, e.target) for e in result.events] == [(GameErrorCode.INVALID_DISCARD, "seat_0")]
        assert result.new_round_state is round_state
        assert result.needs_post_discard is False

    def test_soft_error__when_not_your_turn__should_return_error_event(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_discard(round_state, game_state, seat=1, data=DiscardActionData(tile_id=0))
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.NOT_YOUR_TURN

    def test_soft_error__when_ron_without_pending_prompt__should_return_error_event(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_ron(round_state, game_state, seat=0)
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_RON

    def test_soft_error__when_pass_without_prompt__should_return_error_event(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        result = handle_pass(round_state, game_state, seat=0)
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_PASS

    def test_soft_error__when_pon_tile_mismatches__should_return_error_event(self):
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

    def test_soft_error__when_seat_not_pending__should_return_error_event(self):
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
    def test_open_kan_execution__when_player_in_riichi__should_reject(self):
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
            call_open_kan(round_state, caller_seat=1, discarder_seat=0, tile_id=0, settings=settings)


# --- Phase 3: Error Handling Conversion Tests ---


class TestDiscardRaisesInvalidGameActionError:
    def test_discard__when_tile_not_in_hand__should_raise_invalid_game_action(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        with pytest.raises(InvalidGameActionError, match="discard") as exc_info:
            handle_discard(round_state, game_state, seat=0, data=DiscardActionData(tile_id=999))
        assert exc_info.value.seat == 0


class TestRiichiRaisesInvalidGameActionError:
    def test_riichi__when_tile_not_in_hand__should_raise_invalid_game_action(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        with pytest.raises(InvalidGameActionError, match="declare_riichi") as exc_info:
            handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=999))
        assert exc_info.value.seat == 0

    def test_riichi__when_already_in_riichi__should_raise_invalid_game_action(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        round_state = update_player(round_state, 0, is_riichi=True)
        game_state = game_state.model_copy(update={"round_state": round_state})
        tile_id = round_state.players[0].tiles[0]

        with pytest.raises(InvalidGameActionError, match="declare_riichi"):
            handle_riichi(round_state, game_state, seat=0, data=RiichiActionData(tile_id=tile_id))

    def test_riichi__when_not_enough_points__should_raise_invalid_game_action(self):
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

    def test_riichi__when_hand_open__should_raise_invalid_game_action(self):
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
    def test_tsumo__when_hand_not_winning__should_raise_invalid_game_action(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        with pytest.raises(InvalidGameActionError, match="declare_tsumo") as exc_info:
            handle_tsumo(round_state, game_state, seat=0)
        assert exc_info.value.seat == 0


class TestKanRaisesInvalidGameActionError:
    def test_closed_kan__when_not_enough_tiles__should_raise_invalid_game_action(self):
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state
        # Explicitly set tiles that don't contain 4 of any tile (all distinct in 34-tile space)
        no_kan_tiles = tuple(
            TilesConverter.string_to_136_array(
                man="123456789",
                pin="12345",
            ),
        )
        round_state = update_player(round_state, 0, tiles=no_kan_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        data = KanActionData(tile_id=no_kan_tiles[0], kan_type=KanType.CLOSED)
        with pytest.raises(InvalidGameActionError, match="call_kan"):
            handle_kan(round_state, game_state, seat=0, data=data)


class TestServerGeneratedActionRefusals:
    @pytest.fixture
    def service(self):
        service = MahjongGameService()
        service.start_game("test", ["Player"], seed="a" * 192)
        return service

    def _make_ai_seat_current(self, service):
        ai_player_seat = min(service._ai_player_controllers["test"].ai_player_seats)
        round_state = service._games["test"].round_state.model_copy(update={"current_player_seat": ai_player_seat})
        service._games["test"] = service._games["test"].model_copy(update={"round_state": round_state})
        return ai_player_seat

    def test_ai_call_response__when_handler_refuses_it__should_raise_generated_action_error(self, service):
        game_state = service._games["test"]
        ai_player_seat = min(service._ai_player_controllers["test"].ai_player_seats)
        prompt = PendingCallPrompt(
            call_type=CallType.DISCARD,
            tile_id=0,
            from_seat=(ai_player_seat + 1) % 4,
            pending_seats=frozenset({ai_player_seat}),
            callers=(MeldCaller(seat=ai_player_seat, call_type=MeldCallType.PON),),
        )
        round_state = game_state.round_state.model_copy(update={"pending_call_prompt": prompt})
        service._games["test"] = game_state.model_copy(update={"round_state": round_state})

        with (
            patch.object(AIPlayer, "should_call_pon", return_value=True),
            pytest.raises(GeneratedActionError, match="call_pon refused"),
        ):
            service._dispatch_ai_player_call_responses("test", prompt, [])
        assert service._games["test"].round_state.pending_call_prompt == prompt

    def test_ai_turn__when_its_discard_gets_a_soft_error__should_raise_without_progress(self, service):
        ai_player_seat = self._make_ai_seat_current(service)
        _update_player(service, game_id="test", seat=ai_player_seat, is_riichi=True)
        state_before = service._games["test"]

        with (
            patch.object(AIPlayer, "select_discard", lambda _self, player, _round_state: player.tiles[0]),
            pytest.raises(GeneratedActionError, match="invalid_discard"),
        ):
            service._process_ai_player_followup("test")
        assert service._games["test"] is state_before

    def test_turn_timeout__when_default_discard_is_refused__should_raise_instead_of_kicking(self, service):
        player_seat = service.get_player_seat("test", "Player")
        assert service._games["test"].round_state.current_player_seat == player_seat

        with (
            patch("game.logic.mahjong_service.choose_default_discard", return_value=999),
            pytest.raises(GeneratedActionError, match="discard refused") as exc_info,
        ):
            service.handle_timeout(game_id="test", player_name="Player", timeout_type=TimeoutType.TURN)
        assert isinstance(exc_info.value.__cause__, InvalidGameActionError)

    def test_round_advance_timeout__when_no_round_awaits_confirmation__should_raise(self, service):
        with pytest.raises(GeneratedActionError, match="no round pending confirmation"):
            service.handle_timeout(game_id="test", player_name="Player", timeout_type=TimeoutType.ROUND_ADVANCE)


class TestOpenKanDefenseInDepthGuards:
    def test_open_kan__when_wall_insufficient__should_raise(self):
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
            call_open_kan(round_state, caller_seat=1, discarder_seat=0, tile_id=tile_5m, settings=settings)

    def test_open_kan__when_max_kans_exceeded__should_raise(self):
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
            call_open_kan(round_state, caller_seat=1, discarder_seat=0, tile_id=tile_5m, settings=settings)


class TestRiichiTileNotInHandValidation:
    def test_riichi__when_tenpai_hand_and_tile_not_in_hand__should_raise(self):
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
    def test_chi__when_seat_not_in_callers__should_raise(self):
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
            match="no meld options for this seat",
        ):
            handle_chi(
                round_state,
                game_state,
                seat=1,
                data=ChiActionData(tile_id=tile_id, sequence_tiles=chi_tiles),
            )
