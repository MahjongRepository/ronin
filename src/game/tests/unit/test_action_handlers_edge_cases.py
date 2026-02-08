"""
Unit tests for edge cases in action handlers.

Tests cover previously untested code paths (removed pragma: no cover lines).
"""

from mahjong.tile import TilesConverter

from game.logic.action_handlers import (
    handle_chi,
    handle_kan,
    handle_pon,
    handle_tsumo,
)
from game.logic.action_result import ActionResult
from game.logic.call_resolution import (
    _pick_best_meld_response,
    complete_added_kan_after_chankan_decline,
    resolve_call_prompt,
)
from game.logic.enums import (
    AbortiveDrawType,
    BotType,
    CallType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldCallType,
    RoundPhase,
)
from game.logic.events import (
    CallPromptEvent,
    ErrorEvent,
    RoundEndEvent,
)
from game.logic.game import init_game
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import draw_tile
from game.logic.state import (
    CallResponse,
    MahjongGameState,
    PendingCallPrompt,
)
from game.logic.state_utils import update_player
from game.logic.types import (
    ChiActionData,
    KanActionData,
    MeldCaller,
    PonActionData,
    SeatConfig,
)


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", bot_type=BotType.TSUMOGIRI),
    ]


def _create_frozen_game_state(seed: float = 12345.0) -> MahjongGameState:
    """Create a frozen game state for testing."""
    game_state = init_game(_default_seat_configs(), seed=seed)
    new_round_state, _tile = draw_tile(game_state.round_state)
    return game_state.model_copy(update={"round_state": new_round_state})


class TestPickBestMeldResponse:
    def test_pick_best_meld_with_meld_callers(self):
        """Test _pick_best_meld_response with MeldCaller objects."""
        # create a prompt with MeldCaller objects
        tile_id = 0
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=2, call_type=MeldCallType.CHI),
            ),
        )

        # create responses: seat 1 calls pon, seat 2 calls chi
        responses = [
            CallResponse(seat=1, action=GameAction.CALL_PON),
            CallResponse(seat=2, action=GameAction.CALL_CHI),
        ]

        best = _pick_best_meld_response(responses, prompt)

        # pon has higher priority (1) than chi (2)
        assert best is not None
        assert best.seat == 1
        assert best.action == GameAction.CALL_PON


class TestResolveMeldResponse:
    def test_meld_causes_exhaustive_draw(self):
        """Test that open kan meld call resolves when wall is empty.

        When the wall is empty, the open kan still processes (draws from dead wall).
        The exhaustive draw will be detected on the next draw phase; here we verify
        the meld resolution succeeds and the player gets a turn event.
        """
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # create a minimal wall (just enough for dead wall: 14 tiles)
        # when open kan is called, it will draw from dead wall and leave wall empty
        minimal_wall = list(range(14))
        round_state = round_state.model_copy(
            update={
                "wall": tuple(minimal_wall[:0]),  # empty wall
                "dead_wall": tuple(minimal_wall[0:14]),  # exactly 14 tiles
                "phase": RoundPhase.PLAYING,
            }
        )

        # give player 1 three matching tiles for open kan
        tile_id = TilesConverter.string_to_136_array(man="5")[0]
        player1_tiles = tuple(TilesConverter.string_to_136_array(man="555368", pin="2479", sou="358"))
        round_state = update_player(round_state, 1, tiles=player1_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        # create prompt with open kan response ready to resolve
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.OPEN_KAN),),
            responses=(CallResponse(seat=1, action=GameAction.CALL_KAN),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        # open kan resolves successfully; the player gets a turn to discard
        assert result.new_round_state is not None
        assert result.new_round_state.phase == RoundPhase.PLAYING
        # verify the meld was processed (player 1 has a kan meld)
        assert any(m.type == FrozenMeld.KAN for m in result.new_round_state.players[1].melds)

    def test_resolve_meld_open_kan_four_kans_abort(self):
        """Open kan meld resolution triggers four kans abort, returning early at FINISHED.

        When resolve_call_prompt dispatches to _resolve_meld_response for an open kan,
        and that open kan is the 4th kan across 2+ players, the round ends immediately
        with an abortive draw. This covers action_handlers.py line 207.
        """
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # 3 existing kans across different players
        kan_meld_0 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="1111")),
            opened=True,
            who=0,
            from_who=0,
        )
        kan_meld_1 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(pin="1111")),
            opened=True,
            who=1,
            from_who=1,
        )
        kan_meld_2 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(sou="1111")),
            opened=True,
            who=2,
            from_who=2,
        )

        # seat 3 has 3 matching tiles for open kan on 5m (4th kan)
        tile_id = TilesConverter.string_to_136_array(man="5")[0]
        player3_tiles = tuple(TilesConverter.string_to_136_array(man="555368", pin="2479", sou="358"))
        round_state = update_player(round_state, 0, melds=(kan_meld_0,))
        round_state = update_player(round_state, 1, melds=(kan_meld_1,))
        round_state = update_player(round_state, 2, melds=(kan_meld_2,))
        round_state = update_player(round_state, 3, tiles=player3_tiles)
        round_state = round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # create prompt with open kan response ready to resolve
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset(),
            callers=(MeldCaller(seat=3, call_type=MeldCallType.OPEN_KAN),),
            responses=(CallResponse(seat=3, action=GameAction.CALL_KAN),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        result = resolve_call_prompt(round_state, game_state)

        # four kans abort: round is FINISHED
        assert result.new_round_state is not None
        assert result.new_round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS


class TestCompleteAddedKanAfterChankanDecline:
    def test_four_kans_after_chankan_decline(self):
        """Test that completing added kan after chankan decline can trigger four kans abort.

        Four kans abortive draw requires 4 total kans across 2+ different players.
        Player 0 has 2 kans + 1 pon. Player 1 has 1 kan. Player 0 upgrades pon to 4th kan.
        """
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state, _tile = draw_tile(game_state.round_state)

        # create 2 existing kans for player 0
        kan_tiles_1 = TilesConverter.string_to_136_array(man="1111")
        kan_tiles_2 = TilesConverter.string_to_136_array(man="2222")

        kan_meld_1 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(kan_tiles_1),
            opened=False,
            called_tile=kan_tiles_1[0],
            who=0,
            from_who=0,
        )
        kan_meld_2 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(kan_tiles_2),
            opened=False,
            called_tile=kan_tiles_2[0],
            who=0,
            from_who=0,
        )

        # create 1 existing kan for player 1 (need 2+ players with kans for abort)
        kan_tiles_3 = TilesConverter.string_to_136_array(man="3333")
        kan_meld_3 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(kan_tiles_3),
            opened=True,
            called_tile=kan_tiles_3[0],
            who=1,
            from_who=2,
        )

        # create a pon that will become the 4th kan
        pon_tiles = TilesConverter.string_to_136_array(man="4444")[:3]
        fourth_tile = TilesConverter.string_to_136_array(man="4444")[3]
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        # update player 0 with 2 kans + 1 pon
        player_tiles = (fourth_tile, *round_state.players[0].tiles[:12])
        round_state = update_player(
            round_state,
            0,
            tiles=player_tiles,
            melds=(kan_meld_1, kan_meld_2, pon_meld),
        )
        # update player 1 with 1 kan
        round_state = update_player(
            round_state,
            1,
            melds=(kan_meld_3,),
        )
        game_state = game_state.model_copy(update={"round_state": round_state})

        # complete the 4th kan (added kan)
        new_round_state, _new_game_state, events = complete_added_kan_after_chankan_decline(
            round_state, game_state, caller_seat=0, tile_id=fourth_tile
        )

        # verify abortive draw for four kans
        assert new_round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS


class TestHandleTsumoInvalidHand:
    def test_handle_tsumo_invalid_hand_error(self):
        """Test handle_tsumo when hand doesn't actually win (ValueError raised)."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # give player 0 a non-winning hand (13 random tiles)
        non_winning_tiles = tuple(
            TilesConverter.string_to_136_array(man="13579", pin="1357", sou="135", honors="12")
        )
        round_state = update_player(round_state, 0, tiles=non_winning_tiles)
        game_state = game_state.model_copy(update={"round_state": round_state})

        # call tsumo with invalid hand
        result = handle_tsumo(round_state, game_state, seat=0)

        # verify error event is returned
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_TSUMO


class TestHandlePonMultiCaller:
    def test_handle_pon_multi_caller_waiting(self):
        """Test pon with multiple callers: one responds, waiting for others."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state, _tile = draw_tile(game_state.round_state)

        tile_id = 0
        # give player 1 and player 2 tiles to call pon/chi
        player1_tiles = [tile_id, tile_id + 1, *list(round_state.players[1].tiles)[:-2]]
        round_state = update_player(round_state, 1, tiles=tuple(player1_tiles))

        # create prompt with 2 pending callers: seat 1 can pon, seat 2 can chi
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.PON),
                MeldCaller(seat=2, call_type=MeldCallType.CHI),
            ),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # seat 1 calls pon
        result = handle_pon(round_state, game_state, seat=1, data=PonActionData(tile_id=tile_id))

        # verify empty events (waiting for seat 2)
        assert isinstance(result, ActionResult)
        assert len(result.events) == 0
        assert result.new_round_state is not None
        # verify seat 1 removed from pending, seat 2 still pending
        assert result.new_round_state.pending_call_prompt is not None
        assert 1 not in result.new_round_state.pending_call_prompt.pending_seats
        assert 2 in result.new_round_state.pending_call_prompt.pending_seats


class TestHandleChiTileMismatch:
    def test_handle_chi_tile_mismatch(self):
        """Test chi with wrong tile_id returns error."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # create pending call prompt for chi
        tile_id = 0
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(MeldCaller(seat=1, call_type=MeldCallType.CHI),),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # call chi with mismatched tile_id
        wrong_tile_id = 999
        result = handle_chi(
            round_state,
            game_state,
            seat=1,
            data=ChiActionData(tile_id=wrong_tile_id, sequence_tiles=(1, 2)),
        )

        # verify error event
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_CHI
        assert "mismatch" in error_events[0].message


class TestHandleChiMultiCaller:
    def test_handle_chi_multi_caller_waiting(self):
        """Test chi with multiple callers: one responds, waiting for others."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state, _tile = draw_tile(game_state.round_state)

        tile_id = TilesConverter.string_to_136_array(man="1")[0]
        sequence_tiles = tuple(TilesConverter.string_to_136_array(man="23"))

        # give player 1 tiles for chi
        player1_tiles = tuple(TilesConverter.string_to_136_array(man="236789", pin="2345789"))
        round_state = update_player(round_state, 1, tiles=player1_tiles)

        # create prompt with 2 pending callers
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.CHI),
                MeldCaller(seat=2, call_type=MeldCallType.PON),
            ),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # seat 1 calls chi
        result = handle_chi(
            round_state,
            game_state,
            seat=1,
            data=ChiActionData(tile_id=tile_id, sequence_tiles=sequence_tiles),
        )

        # verify empty events (waiting for seat 2)
        assert isinstance(result, ActionResult)
        assert len(result.events) == 0
        assert result.new_round_state is not None
        # verify seat 1 removed from pending, seat 2 still pending
        assert result.new_round_state.pending_call_prompt is not None
        assert 1 not in result.new_round_state.pending_call_prompt.pending_seats
        assert 2 in result.new_round_state.pending_call_prompt.pending_seats


class TestHandleKanMultiCaller:
    def test_handle_kan_multi_caller_waiting(self):
        """Test open kan with multiple callers: one responds, waiting for others."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state, _tile = draw_tile(game_state.round_state)

        tile_id = TilesConverter.string_to_136_array(man="5")[0]

        # give player 1 three matching tiles for open kan
        player1_tiles = tuple(TilesConverter.string_to_136_array(man="555368", pin="2479", sou="358"))
        round_state = update_player(round_state, 1, tiles=player1_tiles)

        # create prompt with 2 pending callers
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=0,
            pending_seats=frozenset({1, 2}),
            callers=(
                MeldCaller(seat=1, call_type=MeldCallType.OPEN_KAN),
                MeldCaller(seat=2, call_type=MeldCallType.PON),
            ),
        )
        round_state = round_state.model_copy(update={"pending_call_prompt": prompt})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # seat 1 calls open kan
        result = handle_kan(
            round_state, game_state, seat=1, data=KanActionData(tile_id=tile_id, kan_type=KanType.OPEN)
        )

        # verify empty events (waiting for seat 2)
        assert isinstance(result, ActionResult)
        assert len(result.events) == 0
        assert result.new_round_state is not None
        # verify seat 1 removed from pending, seat 2 still pending
        assert result.new_round_state.pending_call_prompt is not None
        assert 1 not in result.new_round_state.pending_call_prompt.pending_seats
        assert 2 in result.new_round_state.pending_call_prompt.pending_seats


class TestHandleKanInvalidValidationError:
    def test_handle_kan_invalid_validation_error(self):
        """Test handle_kan with closed/added kan that raises ValueError."""
        game_state = _create_frozen_game_state()
        round_state = game_state.round_state

        # player 0 tries to call closed kan on a tile they don't have 4 of
        invalid_tile = TilesConverter.string_to_136_array(man="9")[0]

        result = handle_kan(
            round_state, game_state, seat=0, data=KanActionData(tile_id=invalid_tile, kan_type=KanType.CLOSED)
        )

        # verify error event with INVALID_KAN code
        assert isinstance(result, ActionResult)
        error_events = [e for e in result.events if isinstance(e, ErrorEvent)]
        assert len(error_events) == 1
        assert error_events[0].code == GameErrorCode.INVALID_KAN


class TestHandleKanCausesDraw:
    def test_handle_kan_causes_draw(self):
        """Test closed kan that triggers four kans abortive draw.

        Four kans abortive draw requires 4 total kans across 2+ different players.
        Player 0 has 2 kans. Player 1 has 1 kan. Player 0 declares 4th closed kan.
        """
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state, _tile = draw_tile(game_state.round_state)

        # create 2 existing kans for player 0
        kan_tiles_1 = TilesConverter.string_to_136_array(man="1111")
        kan_tiles_2 = TilesConverter.string_to_136_array(man="2222")

        kan_meld_1 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(kan_tiles_1),
            opened=False,
            called_tile=kan_tiles_1[0],
            who=0,
            from_who=0,
        )
        kan_meld_2 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(kan_tiles_2),
            opened=False,
            called_tile=kan_tiles_2[0],
            who=0,
            from_who=0,
        )

        # create 1 existing kan for player 1 (need 2+ players with kans for abort)
        kan_tiles_3 = TilesConverter.string_to_136_array(man="3333")
        kan_meld_3 = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(kan_tiles_3),
            opened=True,
            called_tile=kan_tiles_3[0],
            who=1,
            from_who=2,
        )

        # player 0 has 4 of the 4th tile for a closed kan
        fourth_kan_tiles = TilesConverter.string_to_136_array(man="4444")
        player_tiles = (*fourth_kan_tiles, *list(round_state.players[0].tiles)[:10])
        round_state = update_player(
            round_state,
            0,
            tiles=player_tiles,
            melds=(kan_meld_1, kan_meld_2),
        )
        # update player 1 with their kan
        round_state = update_player(
            round_state,
            1,
            melds=(kan_meld_3,),
        )
        round_state = round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # declare the 4th closed kan
        result = handle_kan(
            round_state,
            game_state,
            seat=0,
            data=KanActionData(tile_id=fourth_kan_tiles[0], kan_type=KanType.CLOSED),
        )

        # verify round ends with four kans abortive draw
        assert result.new_round_state is not None
        assert result.new_round_state.phase == RoundPhase.FINISHED
        round_end_events = [e for e in result.events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS


class TestHandleKanChankanOpportunity:
    def test_handle_kan_chankan_opportunity(self):
        """Test added kan creates chankan prompt, causing handle_kan to return early.

        When handle_kan processes an added kan and a chankan prompt is created,
        the function returns immediately after detecting the prompt in events.
        This covers action_handlers.py line 727.
        """
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state, _tile = draw_tile(game_state.round_state)

        # player 0 has a pon of 1m that can be upgraded to added kan
        pon_tiles = TilesConverter.string_to_136_array(man="111")[:3]
        fourth_tile = TilesConverter.string_to_136_array(man="1111")[3]
        pon_meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        other_tiles_0 = TilesConverter.string_to_136_array(pin="123456789", sou="11")
        player0_tiles = (fourth_tile, *other_tiles_0)
        round_state = update_player(round_state, 0, tiles=player0_tiles, melds=(pon_meld,))

        # player 1 is waiting on 1m (can chankan)
        # hand: 23m 456m 789m 456p 55s = 13 tiles, waiting on 1m and 4m
        waiting_tiles = tuple(TilesConverter.string_to_136_array(man="23456789", pin="456", sou="55"))
        round_state = update_player(round_state, 1, tiles=waiting_tiles)

        round_state = round_state.model_copy(update={"phase": RoundPhase.PLAYING})
        game_state = game_state.model_copy(update={"round_state": round_state})

        # player 0 declares added kan on the 4th 1m tile
        result = handle_kan(
            round_state, game_state, seat=0, data=KanActionData(tile_id=fourth_tile, kan_type=KanType.ADDED)
        )

        # verify chankan prompt is created (handle_kan returns early at line 727)
        assert result.new_round_state is not None
        call_prompt_events = [e for e in result.events if isinstance(e, CallPromptEvent)]
        assert len(call_prompt_events) == 1
        assert call_prompt_events[0].call_type == CallType.CHANKAN
